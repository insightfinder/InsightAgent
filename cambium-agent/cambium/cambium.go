package cambium

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
	"github.com/sirupsen/logrus"

	"cambium-metrics-collector/config"
	"cambium-metrics-collector/insightfinder"
	"cambium-metrics-collector/models"
)

// ===========================================
// GLOBAL CONFIGURATION AND VARIABLES
// ===========================================

// Global configuration
var (
	Cfg       *config.Config
	IfService *insightfinder.Service
)

// Authentication data
var (
	xsrfToken string
	sidCookie string
	authMutex sync.RWMutex
)

// API endpoints (will be set from config)
var (
	BaseURL    string
	DevicesAPI string
	RadiosAPI  string
	ClientsAPI string
	LoginURL   string
)

// Performance settings (will be set from config)
var (
	MaxRetries  int
	WorkerCount int
)

// ===========================================
// HELPER FUNCTIONS
// ===========================================

// Helper function to determine if a URL is an API request
func isAPIRequest(url string) bool {
	apiPatterns := []string{
		"/api/",
		"/v1/",
		"/v2/",
		"/rest/",
		"/graphql",
		"cambiumnetworks.com",
	}

	for _, pattern := range apiPatterns {
		if strings.Contains(url, pattern) {
			return true
		}
	}
	return false
}

// Helper function to extract authentication tokens from headers
func extractAuthTokens(headers map[string]string) {
	authMutex.Lock()
	defer authMutex.Unlock()

	if xsrf, exists := headers["x-xsrf-token"]; exists {
		xsrfToken = xsrf
		logrus.Debugf("Captured XSRF-TOKEN: %s", xsrf)
	}

	if cookies, exists := headers["set-cookie"]; exists {
		cookieLines := strings.Split(cookies, "\n")
		for _, cookieLine := range cookieLines {
			cookieLine = strings.TrimSpace(cookieLine)
			if cookieLine == "" {
				continue
			}

			parts := strings.Split(cookieLine, ";")
			if len(parts) > 0 {
				mainCookie := strings.TrimSpace(parts[0])

				if strings.HasPrefix(mainCookie, "XSRF-TOKEN=") {
					xsrfToken = strings.TrimPrefix(mainCookie, "XSRF-TOKEN=")
					logrus.Debugf("Captured XSRF-TOKEN from cookie: %s", xsrfToken)
				}
				if strings.HasPrefix(mainCookie, "sid=") {
					sidCookie = strings.TrimPrefix(mainCookie, "sid=")
					logrus.Debugf("Captured sid cookie: %s", sidCookie)
				}
			}
		}
	}
}

// Helper function to extract cookies from HTTP response headers
func extractCookiesFromResponse(headers http.Header) (string, string) {
	var newXsrfToken, newSidCookie string

	setCookies := headers["Set-Cookie"]
	for _, cookie := range setCookies {
		parts := strings.Split(cookie, ";")
		if len(parts) > 0 {
			mainCookie := strings.TrimSpace(parts[0])

			if strings.HasPrefix(mainCookie, "XSRF-TOKEN=") {
				newXsrfToken = strings.TrimPrefix(mainCookie, "XSRF-TOKEN=")
				logrus.Debugf("Found new XSRF-TOKEN: %s", newXsrfToken)
			}
			if strings.HasPrefix(mainCookie, "sid=") {
				newSidCookie = strings.TrimPrefix(mainCookie, "sid=")
				logrus.Debugf("Found new sid: %s", newSidCookie)
			}
		}
	}

	return newXsrfToken, newSidCookie
}

// cleanDeviceName cleans and formats the device name according to specific rules
func cleanDeviceName(deviceName string) string {
	if deviceName == "" {
		return deviceName
	}

	// Strip underscores and replace with dots
	deviceName = strings.ReplaceAll(deviceName, "_", ".")

	// Replace colons with hyphens
	deviceName = strings.ReplaceAll(deviceName, ":", "-")

	// Regex to match leading special characters (hyphens, underscores, etc.)
	re := regexp.MustCompile(`^[-_\W]+`)
	cleaned := re.ReplaceAllString(deviceName, "")

	// Trim any remaining whitespace
	cleaned = strings.TrimSpace(cleaned)

	// If the cleaned name is empty, return the original
	if cleaned == "" {
		return deviceName
	}

	return cleaned
}

// Helper function to read and decompress response body
func readResponseBody(resp *http.Response) ([]byte, error) {
	var reader io.Reader = resp.Body

	// Check if response is gzip compressed
	if resp.Header.Get("Content-Encoding") == "gzip" {
		gzipReader, err := gzip.NewReader(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("failed to create gzip reader: %v", err)
		}
		defer gzipReader.Close()
		reader = gzipReader
	}

	return io.ReadAll(reader)
}

// ===========================================
// AUTHENTICATION FUNCTIONS
// ===========================================

// Login using Playwright and capture authentication tokens
func LoginWithPlaywright() error {
	logrus.Info("Starting Playwright login...")

	pw, err := playwright.Run()
	if err != nil {
		return fmt.Errorf("could not start playwright: %v", err)
	}
	defer pw.Stop()

	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(true),
	})
	if err != nil {
		return fmt.Errorf("could not launch browser: %v", err)
	}
	defer browser.Close()

	page, err := browser.NewPage()
	if err != nil {
		return fmt.Errorf("could not create page: %v", err)
	}

	// Listen for responses to capture authentication tokens
	page.OnResponse(func(response playwright.Response) {
		url := response.URL()
		if isAPIRequest(url) {
			headers := response.Headers()
			extractAuthTokens(headers)
		}
	})

	// Navigate to the login page
	logrus.Info("Navigating to login page...")
	if _, err = page.Goto(LoginURL); err != nil {
		return fmt.Errorf("could not goto login page: %v", err)
	}

	time.Sleep(2 * time.Second)

	// Click Sign In button
	logrus.Info("Clicking Sign In button...")
	if err = page.Locator("button:has-text('Sign In'), a[role='button']:has-text('Sign In')").Click(); err != nil {
		return fmt.Errorf("could not click sign in button: %v", err)
	}

	time.Sleep(2 * time.Second)

	// Fill email address
	logrus.Info("Filling email address...")
	if err = page.Locator("input[type='email'], input[name*='email'], input[placeholder*='email' i]").Fill(Cfg.Cambium.Email); err != nil {
		return fmt.Errorf("could not fill email: %v", err)
	}

	// Click Next button
	logrus.Info("Clicking Next button...")
	if err = page.Locator("text=Next").Click(); err != nil {
		return fmt.Errorf("could not click next button: %v", err)
	}

	time.Sleep(2 * time.Second)

	// Fill password
	logrus.Info("Filling password...")
	if err = page.Locator("input[type='password'], input[name*='password']").Fill(Cfg.Cambium.Password); err != nil {
		return fmt.Errorf("could not fill password: %v", err)
	}

	// Check Remember Me checkbox if present
	logrus.Debug("Checking Remember Me checkbox...")
	if err = page.Locator("input[type='checkbox']").Check(); err != nil {
		logrus.Warnf("Could not check remember me checkbox: %v", err)
	}

	// Click Sign In button (final login)
	logrus.Info("Clicking final Sign In button...")
	if err = page.Locator("button:has-text('Sign In'), input[type='submit'][value*='Sign In'], a[role='button']:has-text('Sign In')").Click(); err != nil {
		return fmt.Errorf("could not click final sign in button: %v", err)
	}

	time.Sleep(5 * time.Second)

	// Navigate to the devices page to trigger additional API calls
	logrus.Info("Navigating to devices page...")
	if _, err = page.Goto(DevicesAPI); err != nil {
		return fmt.Errorf("could not goto devices page: %v", err)
	}

	time.Sleep(3 * time.Second)

	// Extract cookies from browser context
	logrus.Debug("Extracting cookies from browser context...")
	cookies, err := page.Context().Cookies()
	if err != nil {
		logrus.Errorf("Error getting cookies: %v", err)
	} else {
		authMutex.Lock()
		for _, cookie := range cookies {
			if cookie.Name == "sid" {
				sidCookie = cookie.Value
				logrus.Debugf("Extracted sid cookie from browser: %s", sidCookie)
			}
			if cookie.Name == "XSRF-TOKEN" {
				xsrfToken = cookie.Value
				logrus.Debugf("Extracted XSRF-TOKEN cookie from browser: %s", xsrfToken)
			}
		}
		authMutex.Unlock()
	}

	if xsrfToken == "" || sidCookie == "" {
		return fmt.Errorf("failed to capture authentication tokens")
	}

	logrus.Info("Login completed successfully!")
	return nil
}

// ===========================================
// HTTP REQUEST FUNCTIONS
// ===========================================

// Make HTTP request with authentication
func makeAuthenticatedRequest(client *http.Client, url string) (*http.Response, error) {
	authMutex.RLock()
	currentXSRF := xsrfToken
	currentSID := sidCookie
	authMutex.RUnlock()

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	// Set headers
	req.Header.Set("User-Agent", "Mozilla/5.0 (Linux; U; Android 4.0.3; ko-kr; LG-L160L Build/IML74K) AppleWebkit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30")
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Accept-Language", "en-US,en;q=0.5")
	req.Header.Set("Referer", DevicesAPI)

	// Set XSRF token header
	if currentXSRF != "" {
		req.Header.Set("X-XSRF-TOKEN", currentXSRF)
	}

	// Set cookies
	cookieString := ""
	if currentSID != "" {
		cookieString += "sid=" + currentSID
	}
	if currentXSRF != "" {
		if cookieString != "" {
			cookieString += "; "
		}
		cookieString += "XSRF-TOKEN=" + currentXSRF
	}

	if cookieString != "" {
		req.Header.Set("Cookie", cookieString)
	}

	return client.Do(req)
}

// Update tokens from response headers
func updateTokensFromHeaders(headers http.Header) bool {
	newXSRF, newSID := extractCookiesFromResponse(headers)
	if newXSRF != "" && newSID != "" {
		authMutex.Lock()
		xsrfToken = newXSRF
		sidCookie = newSID
		authMutex.Unlock()
		logrus.Info("Updated authentication tokens from response headers")
		return true
	}
	return false
}

// Test MAC address with retry and token update
func testMACAddressWithRetry(client *http.Client, macAddress string) (*models.RadiosResponse, error) {
	url := fmt.Sprintf(RadiosAPI, macAddress)

	for attempt := 1; attempt <= MaxRetries; attempt++ {
		resp, err := makeAuthenticatedRequest(client, url)
		if err != nil {
			if attempt == MaxRetries {
				return nil, fmt.Errorf("failed after %d attempts: %v", MaxRetries, err)
			}
			logrus.Warnf("Request failed (attempt %d/%d): %v, retrying...", attempt, MaxRetries, err)
			time.Sleep(time.Duration(attempt) * time.Second)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode == 200 {
			// Read and decompress response body
			bodyBytes, err := readResponseBody(resp)
			if err != nil {
				return nil, fmt.Errorf("failed to read response body: %v", err)
			}

			var radiosResp models.RadiosResponse
			if err := json.Unmarshal(bodyBytes, &radiosResp); err != nil {
				return nil, fmt.Errorf("failed to decode response: %v", err)
			}
			return &radiosResp, nil
		}

		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			logrus.Warnf("Authentication failed (status %d), attempting to update tokens...", resp.StatusCode)
			if updateTokensFromHeaders(resp.Header) && attempt < MaxRetries {
				logrus.Infof("Tokens updated, retrying (attempt %d/%d)...", attempt+1, MaxRetries)
				time.Sleep(time.Duration(attempt) * time.Second)
				continue
			}
		}

		if attempt == MaxRetries {
			return nil, fmt.Errorf("failed after %d attempts, last status: %d", MaxRetries, resp.StatusCode)
		}
		logrus.Warnf("Request failed with status %d (attempt %d/%d), retrying...", resp.StatusCode, attempt, MaxRetries)
		time.Sleep(time.Duration(attempt) * time.Second)
	}

	return nil, fmt.Errorf("unexpected error in retry logic")
}

// Fetch devices from API
func FetchDevices(client *http.Client) (*models.DevicesResponse, error) {
	for attempt := 1; attempt <= MaxRetries; attempt++ {
		logrus.Debugf("Fetching devices (attempt %d/%d)...", attempt, MaxRetries)

		resp, err := makeAuthenticatedRequest(client, DevicesAPI)
		if err != nil {
			if attempt == MaxRetries {
				return nil, fmt.Errorf("failed to fetch devices after %d attempts: %v", MaxRetries, err)
			}
			logrus.Warnf("Request failed (attempt %d/%d): %v, retrying...", attempt, MaxRetries, err)
			time.Sleep(time.Duration(attempt) * time.Second)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode == 200 {
			// Read and decompress response body
			bodyBytes, err := readResponseBody(resp)
			if err != nil {
				if attempt == MaxRetries {
					return nil, fmt.Errorf("failed to read response body after %d attempts: %v", MaxRetries, err)
				}
				logrus.Warnf("Failed to read response body (attempt %d/%d): %v, retrying...", attempt, MaxRetries, err)
				time.Sleep(time.Duration(attempt) * time.Second)
				continue
			}

			var devicesResp models.DevicesResponse
			if err := json.Unmarshal(bodyBytes, &devicesResp); err != nil {
				if attempt == MaxRetries {
					return nil, fmt.Errorf("failed to decode devices response after %d attempts: %v", MaxRetries, err)
				}
				logrus.Warnf("Failed to decode JSON (attempt %d/%d): %v, retrying...", attempt, MaxRetries, err)
				time.Sleep(time.Duration(attempt) * time.Second)
				continue
			}
			logrus.Info("Successfully fetched devices data")
			return &devicesResp, nil
		}

		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			logrus.Warnf("Authentication failed for devices API (status %d), attempting to update tokens...", resp.StatusCode)
			if updateTokensFromHeaders(resp.Header) && attempt < MaxRetries {
				logrus.Infof("Tokens updated, retrying (attempt %d/%d)...", attempt+1, MaxRetries)
				time.Sleep(time.Duration(attempt) * time.Second)
				continue
			}

			// If token update failed and this is the last attempt, try re-login
			if attempt == MaxRetries {
				logrus.Warn("Token update failed, attempting re-login...")
				if err := LoginWithPlaywright(); err != nil {
					return nil, fmt.Errorf("re-login failed: %v", err)
				}
				// Try one more time after re-login
				logrus.Info("Re-login successful, trying devices API again...")
				resp, err := makeAuthenticatedRequest(client, DevicesAPI)
				if err != nil {
					return nil, fmt.Errorf("failed even after re-login: %v", err)
				}
				defer resp.Body.Close()

				if resp.StatusCode == 200 {
					bodyBytes, err := readResponseBody(resp)
					if err != nil {
						return nil, fmt.Errorf("failed to read response body after re-login: %v", err)
					}

					var devicesResp models.DevicesResponse
					if err := json.Unmarshal(bodyBytes, &devicesResp); err != nil {
						return nil, fmt.Errorf("failed to decode devices response after re-login: %v", err)
					}
					logrus.Info("Successfully fetched devices data after re-login")
					return &devicesResp, nil
				}
				return nil, fmt.Errorf("still failed after re-login, status: %d", resp.StatusCode)
			}
		}

		if attempt < MaxRetries {
			logrus.Warnf("Request failed with status %d (attempt %d/%d), retrying...", resp.StatusCode, attempt, MaxRetries)
			time.Sleep(time.Duration(attempt) * time.Second)
		}
	}

	return nil, fmt.Errorf("failed to fetch devices after %d attempts", MaxRetries)
}

// Fetch clients data with retry and token update
func fetchClientsDataWithRetry(client *http.Client, nid string) (*models.ClientsResponse, error) {
	url := fmt.Sprintf(ClientsAPI, nid)

	for attempt := 1; attempt <= MaxRetries; attempt++ {
		resp, err := makeAuthenticatedRequest(client, url)
		if err != nil {
			if attempt == MaxRetries {
				return nil, fmt.Errorf("clients request failed after %d attempts: %v", MaxRetries, err)
			}
			logrus.Warnf("Clients request failed (attempt %d/%d): %v, retrying...", attempt, MaxRetries, err)
			time.Sleep(time.Duration(attempt) * time.Second)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode == 200 {
			// Read and decompress response body
			bodyBytes, err := readResponseBody(resp)
			if err != nil {
				return nil, fmt.Errorf("failed to read clients response body: %v", err)
			}

			var clientsResp models.ClientsResponse
			if err := json.Unmarshal(bodyBytes, &clientsResp); err != nil {
				return nil, fmt.Errorf("failed to unmarshal clients response: %v", err)
			}
			return &clientsResp, nil
		}

		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			logrus.Warnf("Authentication failed (status %d), attempting to update tokens...", resp.StatusCode)
			if !updateTokensFromHeaders(resp.Header) {
				logrus.Warn("Failed to update tokens from response headers")
			}
		}

		if attempt == MaxRetries {
			return nil, fmt.Errorf("clients request failed with status %d after %d attempts", resp.StatusCode, MaxRetries)
		}
		logrus.Warnf("Clients request failed with status %d (attempt %d/%d), retrying...", resp.StatusCode, attempt, MaxRetries)
		time.Sleep(time.Duration(attempt) * time.Second)
	}

	return nil, fmt.Errorf("unexpected error in clients retry logic")
}

// ===========================================
// CLIENT METRICS CALCULATION FUNCTIONS
// ===========================================

// calculateRSSIPercentages calculates the percentage of clients below RSSI thresholds
func calculateRSSIPercentages(clients []models.Client) (below74, below78, below80 float64) {
	if len(clients) == 0 {
		return 0, 0, 0
	}

	var count74, count78, count80 int
	total := len(clients)

	for _, client := range clients {
		if client.RSSI < -74 {
			count74++
		}
		if client.RSSI < -78 {
			count78++
		}
		if client.RSSI < -80 {
			count80++
		}
	}

	below74 = float64(count74) / float64(total) * 100
	below78 = float64(count78) / float64(total) * 100
	below80 = float64(count80) / float64(total) * 100

	return below74, below78, below80
}

// calculateSNRPercentages calculates the percentage of clients below SNR thresholds
func calculateSNRPercentages(clients []models.Client) (below15, below18, below20 float64) {
	if len(clients) == 0 {
		return 0, 0, 0
	}

	var count15, count18, count20 int
	total := len(clients)

	for _, client := range clients {
		if client.SNR < 15 {
			count15++
		}
		if client.SNR < 18 {
			count18++
		}
		if client.SNR < 20 {
			count20++
		}
	}

	below15 = float64(count15) / float64(total) * 100
	below18 = float64(count18) / float64(total) * 100
	below20 = float64(count20) / float64(total) * 100

	return below15, below18, below20
}

// enrichDeviceWithClientMetrics enriches device data with RSSI and SNR from client data
func enrichDeviceWithClientMetrics(device *models.Device, clients []models.Client) {
	if len(clients) == 0 {
		return
	}

	// Calculate average RSSI and SNR from all clients
	var totalRSSI, totalSNR int
	for _, client := range clients {
		totalRSSI += client.RSSI
		totalSNR += client.SNR
	}

	avgRSSI := totalRSSI / len(clients)
	avgSNR := totalSNR / len(clients)

	// Convert RSSI to positive value for backwards compatibility
	positiveRSSI := avgRSSI
	if positiveRSSI < 0 {
		positiveRSSI = -positiveRSSI // Make positive
	}
	device.RSSI = &positiveRSSI
	device.SNR = &avgSNR

	// Calculate percentage metrics
	rssiBelow74, rssiBelow78, rssiBelow80 := calculateRSSIPercentages(clients)
	snrBelow15, snrBelow18, snrBelow20 := calculateSNRPercentages(clients)

	// Add percentage metrics to device
	device.RSSIPercentBelow74 = &rssiBelow74
	device.RSSIPercentBelow78 = &rssiBelow78
	device.RSSIPercentBelow80 = &rssiBelow80
	device.SNRPercentBelow15 = &snrBelow15
	device.SNRPercentBelow18 = &snrBelow18
	device.SNRPercentBelow20 = &snrBelow20
}

// ===========================================
// WORKER POOL FUNCTIONS
// ===========================================

// Worker pool job
type Job struct {
	Device models.Device
	Client *http.Client
}

// Worker pool result
type Result struct {
	MetricData *models.MetricData
	Error      error
}

// Worker function to process device
func worker(jobs <-chan Job, results chan<- Result) {
	for job := range jobs {
		device := job.Device
		client := job.Client

		logrus.Debugf("Processing device: %s (MAC: %s)", device.Name, device.MAC)

		// Try to get radio stats with retry
		radiosResp, err := testMACAddressWithRetry(client, device.MAC)
		if err != nil {
			logrus.Errorf("Failed to get radio stats for device %s: %v", device.MAC, err)
			results <- Result{Error: err}
			continue
		}

		// Create metric data
		cleanName := cleanDeviceName(device.Cfg.Name)
		if cleanName == "" || cleanName == "unknown-device" {
			cleanName = cleanDeviceName(device.Name)
		}

		ipAddress := device.Net.WAN
		if ipAddress == "" {
			ipAddress = device.Net.IP
		}

		metricData := &models.MetricData{
			Timestamp:    time.Now().Unix(),
			InstanceName: cleanName,
			Data: map[string]interface{}{
				// "Status": func() int {
				// 	if device.Sys.Online {
				// 		return 1
				// 	} else {
				// 		return 0
				// 	}
				// }(),
				"Available Memory": device.Sys.Mem,
				"CPU Utilization":  device.Sys.CPU,
			},
			Zone: device.Config.Profile,
			IP:   ipAddress,
		}

		// Add radio data if available
		radios := radiosResp.Data.Radios
		logrus.Debugf("Device %s has %d radios", device.MAC, len(radios))

		// Initialize all radio metrics with default/empty values
		var radio5G, radio6G *models.Radio

		// Parse radios by band
		for _, radio := range radios {
			switch radio.Band {
			// case "2.4 GHz":
			// 	radio24G = &radio
			case "5 GHz":
				radio5G = &radio
			case "6 GHz":
				radio6G = &radio
			}
		}

		// // Add 2.4GHz metrics
		// if radio24G != nil {
		// 	metricData.Data["Num Clients 24G"] = radio24G.Mus
		// 	// metricData.Data["UL Throughput 24G"] = radio24G.UlTPut
		// 	// metricData.Data["DL Throughput 24G"] = radio24G.DlTPut
		// 	metricData.Data["Noise Floor 24G"] = radio24G.Nf
		// 	metricData.Data["Channel Utilization 24G"] = radio24G.TotalCu
		// } else {
		// 	metricData.Data["Num Clients 24G"] = 0
		// 	// metricData.Data["UL Throughput 24G"] = 0.0
		// 	// metricData.Data["DL Throughput 24G"] = 0.0
		// 	metricData.Data["Noise Floor 24G"] = 0.0
		// 	metricData.Data["Channel Utilization 24G"] = 0.0
		// }

		// Add 5GHz metrics
		if radio5G != nil {
			metricData.Data["Num Clients 5G"] = radio5G.Mus
			metricData.Data["Channel Utilization 5G"] = radio5G.TotalCu
			// metricData.Data["UL Throughput 5G"] = radio5G.UlTPut
			// metricData.Data["DL Throughput 5G"] = radio5G.DlTPut
			// metricData.Data["Noise Floor 5G"] = radio5G.Nf
		} else {
			metricData.Data["Num Clients 5G"] = 0
			metricData.Data["Channel Utilization 5G"] = 0.0
			// metricData.Data["UL Throughput 5G"] = 0.0
			// metricData.Data["DL Throughput 5G"] = 0.0
			// metricData.Data["Noise Floor 5G"] = 0.0
		}

		// Add 6GHz metrics
		if radio6G != nil {
			metricData.Data["Num Clients 6G"] = radio6G.Mus
			metricData.Data["Channel Utilization 6G"] = radio6G.TotalCu
			// metricData.Data["UL Throughput 6G"] = radio6G.UlTPut
			// metricData.Data["DL Throughput 6G"] = radio6G.DlTPut
			// metricData.Data["Noise Floor 6G"] = radio6G.Nf
		} else {
			metricData.Data["Num Clients 6G"] = 0
			metricData.Data["Channel Utilization 6G"] = 0.0
			// metricData.Data["UL Throughput 6G"] = 0.0
			// metricData.Data["DL Throughput 6G"] = 0.0
			// metricData.Data["Noise Floor 6G"] = 0.0
		}

		// Check if device is Wi-Fi and has NID for client data
		if (strings.ToLower(device.Mode) == "wi-fi" || strings.ToLower(device.Mode) == "wifi") && device.Nid != "" {
			logrus.Debugf("Device %s is Wi-Fi with NID %s, fetching client data...", device.MAC, device.Nid)

			clientsResp, err := fetchClientsDataWithRetry(client, device.MAC)
			if err != nil {
				logrus.Warnf("Failed to get client data for device %s (MAC: %s): %v", device.MAC, device.MAC, err)
			} else if clientsResp != nil && len(clientsResp.Data.Devices.Clients) > 0 {
				clients := clientsResp.Data.Devices.Clients
				logrus.Debugf("Device %s has %d clients", device.MAC, len(clients))

				// Create a copy of the device and enrich it with client metrics
				deviceCopy := device
				enrichDeviceWithClientMetrics(&deviceCopy, clients)

				// Add client-derived metrics if available
				if deviceCopy.RSSI != nil {
					metricData.Data["RSSI Avg"] = *deviceCopy.RSSI
				}
				if deviceCopy.SNR != nil {
					metricData.Data["SNR Avg"] = *deviceCopy.SNR
				}

				// Add RSSI percentage metrics
				if deviceCopy.RSSIPercentBelow74 != nil {
					metricData.Data["% Clients RSSI < -74 dBm"] = *deviceCopy.RSSIPercentBelow74
				}
				if deviceCopy.RSSIPercentBelow78 != nil {
					metricData.Data["% Clients RSSI < -78 dBm"] = *deviceCopy.RSSIPercentBelow78
				}
				if deviceCopy.RSSIPercentBelow80 != nil {
					metricData.Data["% Clients RSSI < -80 dBm"] = *deviceCopy.RSSIPercentBelow80
				}

				// Add SNR percentage metrics
				if deviceCopy.SNRPercentBelow15 != nil {
					metricData.Data["% Clients SNR < 15 dBm"] = *deviceCopy.SNRPercentBelow15
				}
				if deviceCopy.SNRPercentBelow18 != nil {
					metricData.Data["% Clients SNR < 18 dBm"] = *deviceCopy.SNRPercentBelow18
				}
				if deviceCopy.SNRPercentBelow20 != nil {
					metricData.Data["% Clients SNR < 20 dBm"] = *deviceCopy.SNRPercentBelow20
				}

				logrus.Debugf("Added client metrics for device %s: %d clients processed", device.MAC, len(clients))
			} else {
				logrus.Debugf("Device %s has no clients, skipping client metrics", device.MAC)
			}
		}

		logrus.Debugf("Successfully processed device %s", device.MAC)
		results <- Result{MetricData: metricData}
	}
}

// ===========================================
// METRICS COLLECTION FUNCTIONS
// ===========================================

// Collect metrics for all devices
func CollectMetrics() error {
	logrus.Infof("Starting metrics collection at %s...", time.Now().Format("2006-01-02 15:04:05"))

	client := &http.Client{
		Timeout: 30 * time.Second,
	}

	// Fetch devices
	logrus.Info("Fetching devices list...")
	devicesResp, err := FetchDevices(client)
	if err != nil {
		return fmt.Errorf("failed to fetch devices: %v", err)
	}

	deviceCount := len(devicesResp.Data.Devices)
	logrus.Infof("Found %d devices to process", deviceCount)

	if deviceCount == 0 {
		logrus.Warn("No devices found, skipping metrics collection")
		return nil
	}

	// Create worker pool
	jobs := make(chan Job, deviceCount)
	results := make(chan Result, deviceCount)

	// Start workers
	logrus.Infof("Starting %d workers for device processing...", WorkerCount)
	for w := 1; w <= WorkerCount; w++ {
		go worker(jobs, results)
	}

	// Send jobs
	logrus.Debug("Sending devices to worker pool...")
	for _, device := range devicesResp.Data.Devices {
		jobs <- Job{Device: device, Client: client}
	}
	close(jobs)

	// Collect results
	logrus.Info("Collecting results from workers...")
	var allMetrics []models.MetricData
	successCount := 0
	for i := 0; i < deviceCount; i++ {
		result := <-results
		if result.Error != nil {
			logrus.Errorf("Error processing device %d/%d: %v", i+1, deviceCount, result.Error)
			continue
		}
		if result.MetricData != nil {
			allMetrics = append(allMetrics, *result.MetricData)
			successCount++
			if successCount%500 == 0 || successCount == deviceCount {
				logrus.Infof("Processed %d/%d devices successfully", successCount, deviceCount)
			}
		}
	}

	// Send metrics to InsightFinder
	if len(allMetrics) > 0 {
		logrus.Infof("Sending %d metrics to InsightFinder...", len(allMetrics))
		if err := IfService.SendMetricsBulk(allMetrics); err != nil {
			logrus.Errorf("Failed to send metrics to InsightFinder: %v", err)
			// Still save to file as backup
			logrus.Info("Saving metrics to local file as backup...")
		} else {
			logrus.Infof("Successfully sent %d metrics to InsightFinder", len(allMetrics))
		}
	}

	// Save to final.json as backup/debugging
	// logrus.Debugf("Saving %d metrics to final.json...", len(allMetrics))
	// finalData := map[string]interface{}{
	// 	"timestamp": time.Now().Unix(),
	// 	"metrics":   allMetrics,
	// 	"summary": map[string]interface{}{
	// 		"total_devices":    deviceCount,
	// 		"successful_count": len(allMetrics),
	// 		"failed_count":     deviceCount - len(allMetrics),
	// 		"collection_time":  time.Now().Format("2006-01-02 15:04:05"),
	// 	},
	// }

	// jsonData, err := json.MarshalIndent(finalData, "", "  ")
	// if err != nil {
	// 	return fmt.Errorf("failed to marshal final data: %v", err)
	// }

	// if err := os.WriteFile("final.json", jsonData, 0644); err != nil {
	// 	return fmt.Errorf("failed to write final.json: %v", err)
	// }

	logrus.Infof("Metrics collection completed successfully! Saved %d/%d metrics", len(allMetrics), deviceCount)
	return nil
}

// Background metrics collection with interval
func StartMetricsCollection(intervalSeconds int) {
	logrus.Infof("Starting background metrics collection with %d second interval", intervalSeconds)

	// Run immediately first
	logrus.Info("Running initial metrics collection...")
	if err := CollectMetrics(); err != nil {
		logrus.Errorf("Error in initial metrics collection: %v", err)
		// Try once more immediately with a short delay
		logrus.Info("Retrying initial collection in 5 seconds...")
		time.Sleep(5 * time.Second)
		if err := CollectMetrics(); err != nil {
			logrus.Errorf("Second attempt also failed: %v", err)
		}
	}

	// Set up ticker for interval collection
	ticker := time.NewTicker(time.Duration(intervalSeconds) * time.Second)
	defer ticker.Stop()

	// Then run on interval
	for range ticker.C {
		logrus.Infof("Starting scheduled metrics collection at %s", time.Now().Format("2006-01-02 15:04:05"))
		if err := CollectMetrics(); err != nil {
			logrus.Errorf("Error in scheduled metrics collection: %v", err)
		}
	}
}

// ===========================================
// CONFIGURATION INITIALIZATION
// ===========================================

// Initialize configuration from YAML file
func InitConfig(configPath string) error {
	var err error
	Cfg, err = config.LoadConfig(configPath)
	if err != nil {
		return fmt.Errorf("failed to load configuration: %v", err)
	}

	// Set global variables from config
	BaseURL = Cfg.Cambium.BaseURL
	DevicesAPI = BaseURL + "/tree/devices"
	RadiosAPI = BaseURL + "/stats/devices/%s/radios"
	ClientsAPI = BaseURL + "/stats/devices/%s/clients?fields=$clients,_id,id,eType,ip,ssid,name,rssi,snr,active,mac,type:0,eType:Jaguar,mode:wi-fi,$inventory,cfg&limit=1000&offset=0&sortedBy=name,mac&unconnected=false"
	LoginURL = Cfg.Cambium.LoginURL
	MaxRetries = Cfg.Cambium.MaxRetries
	WorkerCount = Cfg.Cambium.WorkerCount

	// Set up logging
	level, err := logrus.ParseLevel(strings.ToLower(Cfg.Agent.LogLevel))
	if err != nil {
		logrus.Warnf("Invalid log level '%s', defaulting to INFO", Cfg.Agent.LogLevel)
		level = logrus.InfoLevel
	}
	logrus.SetLevel(level)
	logrus.SetFormatter(&logrus.TextFormatter{
		FullTimestamp:   true,
		TimestampFormat: "2006-01-02 15:04:05",
	})

	// Initialize InsightFinder service
	IfService = insightfinder.NewService(Cfg.InsightFinder)
	if !IfService.Validate() {
		return fmt.Errorf("InsightFinder configuration validation failed")
	}

	// Create project if it doesn't exist
	if !IfService.CreateProjectIfNotExist() {
		return fmt.Errorf("failed to create or verify InsightFinder project")
	}

	logrus.Info("Configuration initialized successfully")
	return nil
}

// ===========================================
// PUBLIC API FUNCTIONS
// ===========================================

// Run starts the Cambium metrics collector with the given configuration file
func Run(configPath string) error {
	logrus.Info("=== Cambium Network Metrics Collector ===")

	// Step 1: Initialize configuration
	logrus.Infof("Step 1: Loading configuration from %s...", configPath)
	if err := InitConfig(configPath); err != nil {
		return fmt.Errorf("configuration initialization failed: %v", err)
	}

	// Step 2: Login and capture tokens
	logrus.Info("Step 2: Performing initial login...")
	if err := LoginWithPlaywright(); err != nil {
		return fmt.Errorf("initial login failed: %v", err)
	}

	// Step 3: Start background metrics collection
	intervalSeconds := Cfg.Cambium.CollectionInterval
	logrus.Infof("Step 3: Starting metrics collection every %d seconds...", intervalSeconds)

	StartMetricsCollection(intervalSeconds)
	return nil
}
