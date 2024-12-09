package main

func main() {
	JiraService := CreateJiraService("maoyu@insightfinder.com", "", "https://insightfinders.atlassian.net", "II")
	JiraService.GetTickets("2024-01-01", "2024-12-01")
}
