variable "aws_region" {
  description = "AWS region for S3 bucket"
  type        = string
  default     = "ap-southeast-3"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project   = "vale-indonesia-static"
    ManagedBy = "terraform"
  }
}
