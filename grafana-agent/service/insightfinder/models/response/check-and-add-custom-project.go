package response

type CheckAndAddCustomProjectResponse struct {
	IsSuccess      bool `json:"success"`
	IsProjectExist bool `json:"isProjectExist"`
}
