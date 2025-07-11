
/**
 * Convert Zabbix date/time format to UTC ISO string
 * @param {string} date - Date in format "YYYY.MM.DD"
 * @param {string} time - Time in format "HH:MM:SS"
 * @returns {object} - Object with UTC date and time strings
 */
function convertToUTC(date, time) {
    if (!date || !time) {
        return { date: null, time: null };
    }
    
    try {
        // Parse Zabbix date format (YYYY.MM.DD) and time (HH:MM:SS)
        var dateParts = date.toString().split('.');
        var timeParts = time.toString().split(':');
        
        if (dateParts.length !== 3 || timeParts.length !== 3) {
            Zabbix.Log(1, "[UTC Conversion] Invalid date/time format: " + date + " " + time);
            return { date: null, time: null };
        }
        
        // Create Date object (Note: month is 0-indexed in JavaScript)
        var localDate = new Date(
            parseInt(dateParts[0]),           // year
            parseInt(dateParts[1]) - 1,       // month (0-indexed)
            parseInt(dateParts[2]),           // day
            parseInt(timeParts[0]),           // hour
            parseInt(timeParts[1]),           // minute
            parseInt(timeParts[2])            // second
        );
        
        // Convert to UTC
        var utcDate = new Date(localDate.getTime() + (localDate.getTimezoneOffset() * 60000));
        
        // Format as ISO strings
        var utcDateStr = utcDate.getFullYear() + '-' + 
                        String(utcDate.getMonth() + 1).padStart(2, '0') + '-' + 
                        String(utcDate.getDate()).padStart(2, '0');
        
        var utcTimeStr = String(utcDate.getHours()).padStart(2, '0') + ':' + 
                        String(utcDate.getMinutes()).padStart(2, '0') + ':' + 
                        String(utcDate.getSeconds()).padStart(2, '0');
        
        Zabbix.Log(4, "[UTC Conversion] Local: " + date + " " + time + " -> UTC: " + utcDateStr + " " + utcTimeStr);
        
        return {
            date: utcDateStr,
            time: utcTimeStr
        };
    } catch (error) {
        Zabbix.Log(1, "[UTC Conversion] Error converting to UTC: " + error);
        return { date: null, time: null };
    }
}

/**
 * Add padding to string for consistent formatting
 */
String.prototype.padStart = String.prototype.padStart || function(targetLength, padString) {
    targetLength = targetLength >> 0;
    padString = String(padString || ' ');
    if (this.length >= targetLength) {
        return String(this);
    } else {
        targetLength = targetLength - this.length;
        if (targetLength > padString.length) {
            padString += padString.repeat(targetLength / padString.length);
        }
        return padString.slice(0, targetLength) + String(this);
    }
};

try {
    // Parse parameters from Zabbix webhook
    var params = JSON.parse(value);
    
    // Create HTTP request
    var req = new HttpRequest();
    
    // Check if required parameters are defined
    if (!params.API_KEY) {
        throw 'API_KEY parameter is not configured or empty. Please add API_KEY parameter in media type.';
    }
    
    if (!params.SERVER_URL) {
        throw 'SERVER_URL parameter is not configured or empty. Please add SERVER_URL parameter in media type.';
    }
    
    // Set headers directly in JavaScript code
    req.addHeader('Content-Type: application/json');
    req.addHeader('Authorization: Bearer ' + params.API_KEY);

    // Convert event date/time to UTC
    var eventUTC = convertToUTC(params.event_date, params.event_time);
    
    // Convert recovery date/time to UTC (if present)
    var recoveryUTC = { date: null, time: null };
    if (params.recovery_date && params.recovery_time) {
        recoveryUTC = convertToUTC(params.recovery_date, params.recovery_time);
        Zabbix.Log(4, "[Recovery UTC] Original: " + params.recovery_date + " " + params.recovery_time + 
                    " -> UTC: " + recoveryUTC.date + " " + recoveryUTC.time);
    }

    var payload = {
        // Core alert information
        "alert_subject": params.alert_subject,
        "alert_message": params.alert_message,
        
        // Event details - critical for proper processing
        "event_id": params.event_id,
        "event_name": params.event_name,
        "event_severity": params.event_severity,
        "event_status": params.event_status,
        "event_value": params.event_value,  // Important: 0=OK/resolved, 1=problem
        
        // Event date/time in UTC format
        "event_date": eventUTC.date,       // Format: YYYY-MM-DD (UTC)
        "event_time": eventUTC.time,       // Format: HH:MM:SS (UTC)
        "event_date_original": params.event_date, // Keep original for debugging
        "event_time_original": params.event_time, // Keep original for debugging
        
        // Host information
        "host_name": params.host_name,
        "host_ip": params.host_ip,
        "hostgroup_name": params.hostgroup_name,  // Host group name
                
        // Item details (if available)
        "item_name": params.item_name,
        "item_value": params.item_value,
        
        // Trigger information
        "trigger_id": params.trigger_id,
        "trigger_name": params.trigger_name,
        "trigger_status": params.trigger_status,

        // Recovery information in UTC format (if available)
        "recovery_date": recoveryUTC.date,     // Format: YYYY-MM-DD (UTC)
        "recovery_time": recoveryUTC.time,     // Format: HH:MM:SS (UTC)
        "recovery_date_original": params.recovery_date || null, // Keep original for debugging
        "recovery_time_original": params.recovery_time || null, // Keep original for debugging
    };
    
    // Log the operation with timezone information
    Zabbix.Log(4, "[Zabbix Webhook Agent] Sending webhook to Zabbix Webhook Agent");
    Zabbix.Log(4, "[IF Agent] Host: " + payload.host_name + ", Event: " + payload.event_name);
    Zabbix.Log(4, "[IF Agent] Event Value: " + payload.event_value + " (0=resolved, 1=problem)");
    Zabbix.Log(4, "[IF Agent] Event Time (Local->UTC): " + params.event_date + " " + params.event_time + 
                 " -> " + eventUTC.date + " " + eventUTC.time);
    
    if (recoveryUTC.date && recoveryUTC.time) {
        Zabbix.Log(4, "[IF Agent] Recovery Time (Local->UTC): " + params.recovery_date + " " + params.recovery_time + 
                     " -> " + recoveryUTC.date + " " + recoveryUTC.time);
    }
    
    // Send the request to Zabbix Webhook Agent (URL comes from SERVER_URL parameter)
    Zabbix.Log(3, "Sending webhook to Zabbix Webhook Agent");
    var response = req.post(params.SERVER_URL, JSON.stringify(payload));
    
    // Check response from Zabbix Webhook Agent
    if (req.getStatus() !== 200) {
        throw 'HTTP Error: ' + req.getStatus() + ', Response: ' + response;
    }
    
    // Parse response from Zabbix Webhook Agent
    var responseData = JSON.parse(response);
    
    if (responseData.status === 'success') {
        Zabbix.Log(4, "[Zabbix Webhook Agent] ✅ Successfully processed by Zabbix Webhook Agent");
        Zabbix.Log(4, "[IF Agent] Data forwarded to InsightFinder: " + responseData.data_sent);
        
        // The server handles all the complex logic:
        // - Session management and authentication
        // - Project creation if needed
        // - Data transformation to InsightFinder format
        // - Incident investigation API for resolved events
        // - Error handling and retries
        
        return 'OK - Processed by Zabbix Webhook Agent (InsightFinder: ' + 
               (responseData.data_sent ? 'sent' : 'failed') + ')';
    } else {
        Zabbix.Log(1, "[Zabbix Webhook Agent] ❌ Zabbix Webhook Agent processing failed: " + responseData.message);
        return 'WARNING - ' + responseData.message;
    }
    
} catch (error) {
    Zabbix.Log(1, "[Zabbix Webhook Agent] Error sending to Zabbix Webhook Agent: " + error);
    throw 'Failed to send to Zabbix Webhook Agent: ' + error;
}

/*
PARAMETER CONFIGURATION REQUIRED IN ZABBIX MEDIA TYPE:

**STEP 1: In Administration → Media types → [Your Media Type] → Parameters tab**
**Add these EXACT parameter names and values:**

| Parameter Name       | Parameter Value                                    |
|---------------------|---------------------------------------------------|
| SERVER_URL          | http://your-zabbix-webhook-agent:80/webhook/zabbix/zabbixtest |
| API_KEY             | your_secret_api_key_here                          |
| alert_subject       | {ALERT.SUBJECT}                                   |
| alert_message       | {ALERT.MESSAGE}                                   |
| event_id            | {EVENT.ID}                                        |
| event_name          | {EVENT.NAME}                                      |
| event_severity      | {EVENT.SEVERITY}                                  |
| event_status        | {EVENT.STATUS}                                    |
| event_value         | {EVENT.VALUE}                                     |
| event_date          | {EVENT.DATE}                                      |
| event_time          | {EVENT.TIME}                                      |
| host_name           | {HOST.NAME}                                       |
| host_ip             | {HOST.IP}                                         |
| hostgroup_name      | {TRIGGER.HOSTGROUP.NAME}                          |
| item_name           | {ITEM.NAME}                                       |
| item_value          | {ITEM.VALUE}                                      |
| trigger_id          | {TRIGGER.ID}                                      |
| trigger_name        | {TRIGGER.NAME}                                    |
| trigger_status      | {TRIGGER.STATUS}                                  |
| recovery_time       | {EVENT.RECOVERY.TIME}                             |
| recovery_date       | {EVENT.RECOVERY.DATE}                             |

*/
