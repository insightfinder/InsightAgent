package main

type AuthRequest struct {
	Password string `json:"password" validate:"required"`
	UserName string `json:"userName"`
}

type FlexManagerAuthRequest struct {
	Password string `json:"password" validate:"required"`
	UserName string `json:"userName" validate:"required"`
	Domain   string `json:"domain" validate:"required"`
}

type AuthResponse struct {
	ApiKey    string `json:"apiKey" validate:"required"`
	ApiSecret string `json:"apiSecret" validate:"required"`
	Domain    string `json:"domain" validate:"required"`
	Role      string `json:"role" validate:"required"`
	UserId    string `json:"userId" validate:"required"`
	UserName  string `json:"userName" validate:"required"`
}
