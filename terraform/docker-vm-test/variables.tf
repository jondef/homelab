#Blank var for use by terraform.tfvars
variable "token_secret" {
  type        = string
  description = "The token secret XXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX"
}
#Blank var for use by terraform.tfvars
variable "token_id" {
  type        = string
  description = "ID of the token"
}

variable "virtual_environment_endpoint" {
  type        = string
  description = "The endpoint for the Proxmox Virtual Environment API with trailing slash (example: https://host:port/)"
}

variable "virtual_environment_username" {
  type        = string
  description = "The username and realm for the Proxmox Virtual Environment API (example: root@pam)"
}
