// Enhanced Zabbix Media Type Script for Zabbix Webhook Agent
// This script uses Parameters for macro resolution instead of hardcoded | SERVER_URL          | http://your-zabbix-webhook-agent:80/webhook/zabbix/zabbixtest |alues
// Macros are resolved in Parameters section, not in JavaScript code

// IMPORTANT: Configure these Parameters in your Zabbix Media Type:
// SERVER_URL = http://your-zabbix-webhook-agent:80/webhook/zabbix/zabbixtest
// API_KEY = your_secret_api_key_here
// alert_id = {ALERT.ID}
// alert_subject = {ALERT.SUBJECT}
// alert_message = {ALERT.MESSAGE}
// event_id = {EVENT.ID}
// event_name = {EVENT.NAME}
// event_severity = {EVENT.SEVERITY}
// event_status = {EVENT.STATUS}
// event_value = {EVENT.VALUE}
// event_date = {EVENT.DATE}
// event_time = {EVENT.TIME}
// event_timestamp = {EVENT.TIMESTAMP}
// host_name = {HOST.NAME}
// host_ip = {HOST.IP}
// host_description = {HOST.DESCRIPTION}
// host_metadata = {HOST.METADATA}
// hostgroup_name = {HOSTGROUP.NAME}
// item_name = {ITEM.NAME}
// item_key = {ITEM.KEY}
// item_value = {ITEM.VALUE}
// item_description = {ITEM.DESCRIPTION}
// trigger_id = {TRIGGER.ID}
// trigger_name = {TRIGGER.NAME}
// trigger_description = {TRIGGER.DESCRIPTION}
// trigger_severity = {TRIGGER.SEVERITY}
// trigger_status = {TRIGGER.STATUS}
// trigger_url = {TRIGGER.URL}
// user_fullname = {USER.FULLNAME}
// user_name = {USER.NAME}
// event_recovery_id = {EVENT.RECOVERY.ID}
// event_update_status = {EVENT.UPDATE.STATUS}

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
        "event_date": params.event_date,   // Format: YYYY.MM.DD or YYYY-MM-DD
        "event_time": params.event_time,   // Format: HH:MM:SS
        
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
    };
    
    // Log the operation
    Zabbix.Log(4, "[Zabbix Webhook Agent] Sending webhook to Zabbix Webhook Agent");
    Zabbix.Log(4, "[IF Agent] Host: " + payload.host_name + ", Event: " + payload.event_name);
    Zabbix.Log(4, "[IF Agent] Event Value: " + payload.event_value + " (0=resolved, 1=problem)");
    
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
| SERVER_URL          | http://your-zabbix-webhook-agent:8000/webhook/zabbix/zabbixtest |
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
| hostgroup_name      | {TRIGGER.HOSTGROUP.NAME}                                  |
| item_name           | {ITEM.NAME}                                       |
| item_value          | {ITEM.VALUE}                                      |
| trigger_id          | {TRIGGER.ID}                                      |
| trigger_name        | {TRIGGER.NAME}                                    |
| trigger_status      | {TRIGGER.STATUS}                                  |

**CRITICAL**: The first two parameters (SERVER_URL and API_KEY) are REQUIRED!
Without them, you'll get "undefined" errors.

**IMPORTANT**: Parameter names must match EXACTLY (case-sensitive).
Zabbix passes these as JSON object properties via the `value` variable.

BENEFITS OF USING ZABBIX WEBHOOK AGENT vs DIRECT JAVASCRIPT:

1. SESSION MANAGEMENT: Server handles login tokens and session cookies
2. PROJECT MANAGEMENT: Automatic project creation and validation  
3. ERROR HANDLING: Robust retry logic and error recovery
4. INCIDENT INVESTIGATION: Automatic API calls for resolved events
5. SCALABILITY: Can handle multiple Zabbix instances and projects
6. MONITORING: Built-in metrics and health checks
7. MAINTENANCE: Centralized configuration and updates
8. SECURITY: API key authentication vs embedding credentials
9. EXTENSIBILITY: Easy to add new destinations and processors
10. DEBUGGING: Centralized logging and troubleshooting

WHAT THE SERVER DOES AUTOMATICALLY:
- Validates and transforms Zabbix webhook data
- Creates safe instance names (host.name -> host-name)
- Handles timestamp parsing and formatting
- Determines event type (PROBLEM vs RESOLVED)
- Sends both metric and log data to InsightFinder
- Calls incident investigation API for resolved events
- Manages InsightFinder sessions and authentication
- Creates projects if they don't exist
- Provides detailed logging and metrics
- Handles errors gracefully without failing alerts

CONFIGURATION ON ZABBIX WEBHOOK AGENT:
- INSIGHTFINDER_USERNAME: Your InsightFinder username
- INSIGHTFINDER_PASSWORD: Your InsightFinder password (for session management)
- INSIGHTFINDER_LICENSE_KEY: Your license key
- INSIGHTFINDER_PROJECT_NAME: Target project name
- API_KEY: Authentication key for webhook access
*/
