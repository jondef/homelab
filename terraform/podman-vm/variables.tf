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

# Installed on the VM for the ubuntu user by cloud-init, so this is the key that
# gets you in after a rebuild. Kept as a variable rather than an absolute path so
# terraform can run from any machine, not just one particular laptop.
variable "ssh_public_key_path" {
  type        = string
  description = "Path to the public key to authorise for the ubuntu user on the VM"
  default     = "~/.ssh/id_rsa.pub"
}
