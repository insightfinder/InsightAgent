package main

import (
	"context"
	"fmt"
	"log"
	"sync"

	"github.com/carlmjohnson/requests"
	"github.com/thedevsaddam/gojsonq/v2"
)

type Jira struct {
	Username string
	ApiKey   string
	Url      string
	Project  string
}

func CreateJiraService(username, apiKey, url, project string) Jira {
	return Jira{
		Username: username,
		ApiKey:   apiKey,
		Url:      url,
		Project:  project,
	}
}

func (j *Jira) GetTickets(startDate, endDate string) {
	totalResults := j.getTotalResultsNum(startDate, endDate)
	maxResultsPerQuery := 30
	maxWorkers := 20
	sem := make(chan struct{}, maxWorkers)

	wg := sync.WaitGroup{}

	// Create a channel to store the issues
	issuesChn := make(chan *any, totalResults*2)
	resultsChn := make(chan *map[string]any, totalResults*2)

	for i := 0; i < totalResults; i += maxResultsPerQuery {
		sem <- struct{}{}
		go func(wg *sync.WaitGroup) {
			defer wg.Done()
			defer func() { <-sem }()
			wg.Add(1)
			j.getIssues(i, maxResultsPerQuery, startDate, endDate, &issuesChn)
		}(&wg)
	}
	wg.Wait()
	//close(issuesChn)

	// Start a new goroutine to write the results to files under ./data
	go func() {
		for result := range resultsChn {

			// Get the issue key
			issueKey := (*result)["key"].(string)

			// Write the issue to a file
			WriteToFile(issueKey, result)
		}
	}()

	// Get comments for each issue
	for issue := range issuesChn {
		sem <- struct{}{}
		go func(wg *sync.WaitGroup, issue *any) {
			defer wg.Done()
			defer func() { <-sem }()
			wg.Add(1)

			jq := gojsonq.New().FromInterface(*issue)
			issueKey := jq.Find("key").(string)
			comments := j.GetComments(issueKey)

			// Convert the issue to a map
			issueMap, err := (*issue).(map[string]any)
			if err != true {
				log.Fatalf("Error converting issue to map: %v", err)
			}

			// Add the comments to the issue map
			issueMap["comments"] = *comments

			// Send the issue to the results channel
			resultsChn <- &issueMap
		}(&wg, issue)
	}

	// Wait for all the goroutines to finish
	wg.Wait()
	close(resultsChn)

}

func (j *Jira) GetComments(issueKey string) *[]any {

	// Get the comments
	var commentResponse JiraCommentResponse

	err := requests.
		URL(fmt.Sprintf("%s/rest/api/2/issue/%s/comment", j.Url, issueKey)).
		Bearer(j.ApiKey).
		ToJSON(&commentResponse).
		Fetch(context.Background())
	if err != nil {
		log.Fatalf("Error querying Jira API: %v", err)
	}

	return &commentResponse.Comments
}

func (j *Jira) getIssues(startAt, maxResults int, startDate, endDate string, issuesChn *chan *any) {
	// Get the issues
	var searchResponse JiraSearchResponse

	searchPayload := map[string]string{
		//"jql":        fmt.Sprintf("project=%s AND created >= '%s' AND created <= '%s' ORDER BY created DESC", j.Project, startDate, endDate),
		"jql":        fmt.Sprintf("project=%s ORDER BY created DESC", j.Project),
		"startAt":    fmt.Sprintf("%d", startAt),
		"maxResults": fmt.Sprintf("%d", maxResults),
	}

	err := requests.
		URL(fmt.Sprintf("%s/rest/api/2/search", j.Url)).
		BasicAuth(j.Username, j.ApiKey).
		Bearer(j.ApiKey).
		BodyJSON(searchPayload).
		ToJSON(&searchResponse).
		Post().
		Fetch(context.Background())
	if err != nil {
		log.Fatalf("Error querying Jira API: %v", err)
	}

	// Send the issues to the channel
	for _, issue := range searchResponse.Issues {
		fmt.Println("Add one issue to process queue")
		*issuesChn <- &issue
	}

}

func (j *Jira) getTotalResultsNum(startDate, endDate string) int {
	// Get the query stats
	var searchResponse JiraSearchResponse

	searchPayload := map[string]string{
		//"jql":        fmt.Sprintf("project=%s AND created >= '%s' AND created <= '%s' ORDER BY created DESC", j.Project, startDate, endDate),
		"jql":        fmt.Sprintf("project=%s ORDER BY created DESC", j.Project),
		"startAt":    "0",
		"maxResults": "0",
	}

	err := requests.
		URL(fmt.Sprintf("%s/rest/api/2/search", j.Url)).
		Bearer(j.ApiKey).
		BodyJSON(searchPayload).
		ToJSON(&searchResponse).
		Post().
		Fetch(context.Background())
	if err != nil {
		log.Fatalf("Error querying Jira API: %v", err)
	}
	fmt.Println("Fetching resources: ", searchResponse.Total)
	return searchResponse.Total
}
