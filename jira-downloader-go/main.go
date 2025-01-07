package main

func main() {
	JiraService := CreateJiraService("mwang56@", "", "https://jira..com", "CSWIM")
	JiraService.GetTickets("2024-01-01", "2024-12-09")
}
