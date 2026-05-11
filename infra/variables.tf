variable "domain_name" {
  description = "Domain name for the static site (e.g. indonesia.vale.com)"
  type        = string
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID for the domain"
  type        = string
}

variable "aws_region" {
  description = "AWS region for S3 bucket"
  type        = string
  default     = "ap-southeast-1"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project   = "vale-indonesia-static"
    ManagedBy = "terraform"
  }
}
