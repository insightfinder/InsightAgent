-- Fluent Bit Lua filter that turns log records into InsightFinder log payloads.
--
-- InsightFinder's /api/v1/customprojectrawdata endpoint accepts a JSON body:
--   {
--     "userName": "...", "licenseKey": "...", "projectName": "...",
--     "systemName": "...", "insightAgentType": "LogStreaming",
--     "logDataList": [
--       {"timestamp": <epoch ms>, "tag": "<instance>", "componentName": "...", "data": "<log line>"}
--     ]
--   }
--
-- Fluent Bit's http output cannot wrap records in an envelope like this, so this
-- filter buffers log records, and emits one record per batch whose "body" field
-- holds the full JSON payload and whose "headers" field holds the request
-- headers. The http output posts them as-is (body_key $body, headers_key $headers).
--
-- A batch is emitted when it reaches IF_BATCH_SIZE records or IF_BATCH_BYTES
-- bytes, or when a "tick" record (from the dummy input, once per second)
-- arrives and the oldest buffered record is at least IF_FLUSH_INTERVAL seconds
-- old. Tick records themselves are dropped.
--
-- Settings come from environment variables (see README.md).

local function env(name, default)
    local v = os.getenv(name)
    if v == nil or v == "" then
        return default
    end
    return v
end

local function hostname()
    local h = os.getenv("HOSTNAME")
    if h == nil or h == "" then
        local f = io.open("/etc/hostname", "r")
        if f then
            h = f:read("*l")
            f:close()
        end
    end
    if h == nil or h == "" then
        h = "fluent-bit"
    end
    -- Keep only the short hostname, like the Go agents do
    return (h:gsub("%..*$", ""))
end

local USER_NAME      = env("IF_USER_NAME", "")
local LICENSE_KEY    = env("IF_LICENSE_KEY", "")
local PROJECT_NAME   = env("IF_PROJECT_NAME", "")
local SYSTEM_NAME    = env("IF_SYSTEM_NAME", "")
local INSTANCE_NAME  = env("IF_INSTANCE_NAME", hostname())
local COMPONENT_NAME = env("IF_COMPONENT_NAME", "")
local INSTANCE_FIELD = env("IF_INSTANCE_FIELD", "")
local COMPONENT_FIELD = env("IF_COMPONENT_FIELD", "")
local MESSAGE_KEY    = env("IF_MESSAGE_KEY", "log")
local TICK_TAG       = env("IF_TICK_TAG", "if.tick")
local BATCH_SIZE     = tonumber(env("IF_BATCH_SIZE", "1000"))
local BATCH_BYTES    = tonumber(env("IF_BATCH_BYTES", "2000000"))
local FLUSH_INTERVAL = tonumber(env("IF_FLUSH_INTERVAL", "5"))

if USER_NAME == "" or LICENSE_KEY == "" or PROJECT_NAME == "" then
    io.stderr:write("[insightfinder.lua] IF_USER_NAME, IF_LICENSE_KEY and IF_PROJECT_NAME must be set\n")
end

---------------------------------------------------------------------------
-- Minimal JSON encoder (Fluent Bit's Lua runtime has no JSON library)
---------------------------------------------------------------------------

local ESCAPES = {
    ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
    ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t',
}

local function encode_string(s)
    local escaped = s:gsub('[%c"\\]', function(c)
        return ESCAPES[c] or string.format("\\u%04x", c:byte())
    end)
    return '"' .. escaped .. '"'
end

local encode

local function is_array(t)
    local n = #t
    if n == 0 then
        return false
    end
    local count = 0
    for _ in pairs(t) do
        count = count + 1
    end
    return count == n
end

encode = function(v)
    local t = type(v)
    if t == "string" then
        return encode_string(v)
    elseif t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then
            return "null"
        end
        if v == math.floor(v) and math.abs(v) < 2^53 then
            return string.format("%d", v)
        end
        return string.format("%.17g", v)
    elseif t == "boolean" then
        return tostring(v)
    elseif t == "table" then
        local parts = {}
        if is_array(v) then
            for i = 1, #v do
                parts[#parts + 1] = encode(v[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        for k, val in pairs(v) do
            parts[#parts + 1] = encode_string(tostring(k)) .. ":" .. encode(val)
        end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return "null"
end

---------------------------------------------------------------------------
-- Batching
---------------------------------------------------------------------------

local buffer = {}       -- encoded logDataList entries
local buffer_bytes = 0
local first_buffered_at = nil

local ENVELOPE_PREFIX = "{"
    .. '"userName":' .. encode_string(USER_NAME) .. ","
    .. '"licenseKey":' .. encode_string(LICENSE_KEY) .. ","
    .. '"projectName":' .. encode_string(PROJECT_NAME) .. ","
    .. '"systemName":' .. encode_string(SYSTEM_NAME) .. ","
    .. '"insightAgentType":"LogStreaming",'
    .. '"logDataList":['

local REQUEST_HEADERS = {
    ["Content-Type"] = "application/json",
    ["agent-type"] = "Stream",
}

local function take_batch()
    local body = ENVELOPE_PREFIX .. table.concat(buffer, ",") .. "]}"
    buffer = {}
    buffer_bytes = 0
    first_buffered_at = nil
    return { body = body, headers = REQUEST_HEADERS }
end

-- Clean names the same way the Go agents do (CleanDeviceName)
local function clean_name(s)
    s = s:gsub("_", ".")
    s = s:gsub(":", "-")
    s = s:gsub("[%[%]{}%s,]", "")
    return s
end

local function to_log_entry(timestamp, record)
    local instance = INSTANCE_NAME
    if INSTANCE_FIELD ~= "" and record[INSTANCE_FIELD] ~= nil then
        instance = tostring(record[INSTANCE_FIELD])
    end

    local component = COMPONENT_NAME
    if COMPONENT_FIELD ~= "" and record[COMPONENT_FIELD] ~= nil then
        component = tostring(record[COMPONENT_FIELD])
    end

    -- A plain tailed line only has the message key: send it as a string.
    -- A parsed (e.g. JSON) record has more fields: send the whole record.
    local data = record
    local only_message = record[MESSAGE_KEY] ~= nil
    if only_message then
        for k in pairs(record) do
            if k ~= MESSAGE_KEY then
                only_message = false
                break
            end
        end
    end
    if only_message then
        data = record[MESSAGE_KEY]
    end

    return "{"
        .. '"timestamp":' .. string.format("%d", math.floor(timestamp * 1000)) .. ","
        .. '"tag":' .. encode_string(clean_name(instance)) .. ","
        .. '"componentName":' .. encode_string(clean_name(component)) .. ","
        .. '"data":' .. encode(data)
        .. "}"
end

function to_insightfinder(tag, timestamp, record)
    if tag == TICK_TAG then
        if first_buffered_at ~= nil and os.time() - first_buffered_at >= FLUSH_INTERVAL then
            return 1, timestamp, take_batch()
        end
        return -1, timestamp, record
    end

    local entry = to_log_entry(timestamp, record)
    buffer[#buffer + 1] = entry
    buffer_bytes = buffer_bytes + #entry + 1
    if first_buffered_at == nil then
        first_buffered_at = os.time()
    end

    if #buffer >= BATCH_SIZE or buffer_bytes >= BATCH_BYTES then
        return 1, timestamp, take_batch()
    end
    return -1, timestamp, record
end
