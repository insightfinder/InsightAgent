package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func WriteToFile(issueKey string, result *map[string]any) {
	// Convert the map to JSON
	jsonData, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Printf("Error marshaling data to JSON: %v\n", err)
		return
	}

	// Define the file name
	fileName := fmt.Sprintf("./data/%s.json", issueKey)

	// Create or open the file
	file, err := os.Create(fileName)
	if err != nil {
		fmt.Printf("Error creating file %s: %v\n", fileName, err)
		return
	}
	defer file.Close()

	// Write JSON data to the file
	_, err = file.Write(jsonData)
	if err != nil {
		fmt.Printf("Error writing data to file %s: %v\n", fileName, err)
		return
	}

	fmt.Printf("Data successfully written to %s\n", fileName)
}
