package netexperience

import (
	"fmt"
	"time"

	"github.com/insightfinder/netexperience-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// RefreshCustomerCache refreshes the customer cache
func (s *Service) RefreshCustomerCache() error {
	s.cacheMutex.Lock()
	defer s.cacheMutex.Unlock()

	logrus.Info("Starting customer cache refresh...")
	startTime := time.Now()

	customers, err := s.GetCustomers()
	if err != nil {
		return fmt.Errorf("failed to refresh customer cache: %w", err)
	}

	// Update cache
	s.cache.Customers = make(map[int]*models.Customer)
	for _, customer := range customers {
		s.cache.Customers[customer.ID] = customer
	}
	s.cache.LastCustomerRefresh = time.Now()

	duration := time.Since(startTime)
	logrus.Infof("Customer cache refreshed with %d customers in %v", len(customers), duration.Round(time.Millisecond))
	return nil
}

// RefreshEquipmentCache refreshes the equipment cache for all customers
func (s *Service) RefreshEquipmentCache() error {
	s.cacheMutex.RLock()
	customers := make([]*models.Customer, 0, len(s.cache.Customers))
	for _, customer := range s.cache.Customers {
		customers = append(customers, customer)
	}
	s.cacheMutex.RUnlock()

	if len(customers) == 0 {
		return fmt.Errorf("no customers in cache, refresh customer cache first")
	}

	logrus.Infof("Starting equipment cache refresh for %d customers...", len(customers))
	startTime := time.Now()

	// Fetch equipment for all customers
	newEquipmentCache := make(map[int][]*models.Equipment)
	totalEquipment := 0
	processedCustomers := 0
	failedCustomers := 0

	for _, customer := range customers {
		equipment, err := s.GetEquipmentForCustomer(customer.ID)
		if err != nil {
			logrus.Warnf("Failed to get equipment for customer %d (%s): %v", customer.ID, customer.Name, err)
			failedCustomers++
			continue
		}
		newEquipmentCache[customer.ID] = equipment
		totalEquipment += len(equipment)
		processedCustomers++

		// Log progress every 10 customers
		if processedCustomers%10 == 0 {
			percentage := float64(processedCustomers) / float64(len(customers)) * 100
			logrus.Infof("Progress: %d/%d customers (%.1f%%) | Equipment found: %d | Failed: %d",
				processedCustomers, len(customers), percentage, totalEquipment, failedCustomers)
		}
	}

	s.cacheMutex.Lock()
	s.cache.EquipmentByCustomer = newEquipmentCache
	s.cache.LastEquipmentRefresh = time.Now()
	s.cacheMutex.Unlock()

	duration := time.Since(startTime)
	logrus.Infof("Equipment cache refreshed: %d equipment items across %d customers in %v",
		totalEquipment, processedCustomers, duration.Round(time.Millisecond))
	return nil
}

// RefreshEquipmentIPCache refreshes the IP addresses for all equipment in the cache
func (s *Service) RefreshEquipmentIPCache() error {
	s.cacheMutex.RLock()
	equipmentByCustomer := make(map[int][]*models.Equipment)
	for custID, equipList := range s.cache.EquipmentByCustomer {
		equipmentByCustomer[custID] = equipList
	}
	s.cacheMutex.RUnlock()

	if len(equipmentByCustomer) == 0 {
		return fmt.Errorf("no equipment in cache, refresh equipment cache first")
	}

	// Count total equipment
	totalEquipment := 0
	for _, equipList := range equipmentByCustomer {
		totalEquipment += len(equipList)
	}

	logrus.Infof("Starting IP address refresh for %d equipment items...", totalEquipment)

	totalUpdated := 0
	totalFailed := 0
	progressInterval := 50 // Log progress every 50 items
	startTime := time.Now()
	lastProgressTime := startTime

	// Iterate through all equipment and fetch IP addresses
	for customerID, equipmentList := range equipmentByCustomer {
		for _, equipment := range equipmentList {
			ipAddr, err := s.GetEquipmentIPAddress(customerID, equipment.ID)
			if err != nil {
				logrus.Warnf("Failed to get IP address for equipment %d (customer %d): %v", equipment.ID, customerID, err)
				totalFailed++
				continue
			}

			// Update the equipment IP address in cache
			s.cacheMutex.Lock()
			for _, cachedEquip := range s.cache.EquipmentByCustomer[customerID] {
				if cachedEquip.ID == equipment.ID {
					cachedEquip.IPAddress = ipAddr
					totalUpdated++
					break
				}
			}
			s.cacheMutex.Unlock()

			// Log progress periodically
			totalProcessed := totalUpdated + totalFailed
			if totalProcessed%progressInterval == 0 {
				elapsed := time.Since(lastProgressTime)
				rate := float64(progressInterval) / elapsed.Seconds()
				percentage := float64(totalProcessed) / float64(totalEquipment) * 100
				remainingItems := totalEquipment - totalProcessed
				estimatedTimeRemaining := time.Duration(float64(remainingItems)/rate) * time.Second

				logrus.Infof("Progress: %d/%d (%.1f%%) | Rate: %.1f req/s | Updated: %d | Failed: %d | ETA: %v",
					totalProcessed, totalEquipment, percentage, rate, totalUpdated, totalFailed, estimatedTimeRemaining.Round(time.Second))
				lastProgressTime = time.Now()
			}
		}
	}

	s.cacheMutex.Lock()
	s.cache.LastIPRefresh = time.Now()
	s.cacheMutex.Unlock()

	totalDuration := time.Since(startTime)
	avgRate := float64(totalUpdated+totalFailed) / totalDuration.Seconds()
	logrus.Infof("Equipment IP cache refreshed: %d updated, %d failed in %v (avg rate: %.1f req/s)",
		totalUpdated, totalFailed, totalDuration.Round(time.Second), avgRate)
	return nil
}

// ShouldRefreshEquipmentIPCache checks if equipment IP cache needs refresh
func (s *Service) ShouldRefreshEquipmentIPCache() bool {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	// Check if we have any equipment in cache
	hasEquipment := false
	for _, equipList := range s.cache.EquipmentByCustomer {
		if len(equipList) > 0 {
			hasEquipment = true
			break
		}
	}

	if !hasEquipment {
		return false // No equipment to refresh IPs for
	}

	// Check if LastIPRefresh is zero (never refreshed)
	if s.cache.LastIPRefresh.IsZero() {
		return true
	}

	hoursSinceRefresh := time.Since(s.cache.LastIPRefresh).Hours()
	return hoursSinceRefresh >= float64(s.config.EquipmentIPCacheRefreshHours)
}

// ShouldRefreshCustomerCache checks if customer cache needs refresh
func (s *Service) ShouldRefreshCustomerCache() bool {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	if len(s.cache.Customers) == 0 {
		return true
	}

	hoursSinceRefresh := time.Since(s.cache.LastCustomerRefresh).Hours()
	return hoursSinceRefresh >= float64(s.config.CustomerCacheRefreshHours)
}

// ShouldRefreshEquipmentCache checks if equipment cache needs refresh
func (s *Service) ShouldRefreshEquipmentCache() bool {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	if len(s.cache.EquipmentByCustomer) == 0 {
		return true
	}

	hoursSinceRefresh := time.Since(s.cache.LastEquipmentRefresh).Hours()
	return hoursSinceRefresh >= float64(s.config.EquipmentCacheRefreshHours)
}

// GetCachedCustomers returns all cached customers
func (s *Service) GetCachedCustomers() []*models.Customer {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	customers := make([]*models.Customer, 0, len(s.cache.Customers))
	for _, customer := range s.cache.Customers {
		customers = append(customers, customer)
	}
	return customers
}

// GetCachedEquipmentForCustomer returns cached equipment for a customer
func (s *Service) GetCachedEquipmentForCustomer(customerID int) []*models.Equipment {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	return s.cache.EquipmentByCustomer[customerID]
}

// GetCachedCustomer returns a specific customer from cache
func (s *Service) GetCachedCustomer(customerID int) *models.Customer {
	s.cacheMutex.RLock()
	defer s.cacheMutex.RUnlock()

	return s.cache.Customers[customerID]
}
