#  Variables.tf declares the default variables that are shared by all environments
# $var.region, $var.domain, $var.tf_s3_bucket

# This should be changed to reflect the service / stack defined by this repo
variable "stack" {
  default = "commcarehq"
}

variable "tf_s3_bucket" {
  description = "S3 bucket Terraform can use for state"
  default     = "dimagi-terraform"
}

module "network" {
  source            = "../network"
  vpc_begin_range   = "${var.vpc_begin_range}"
  env               = "${var.environment}"
  azs               = "${var.azs}"
  az_codes          = "${var.az_codes}"
  vpn_connections   = "${var.vpn_connections}"
  vpn_connection_routes = "${var.vpn_connection_routes}"
  external_routes   = "${var.external_routes}"
}


locals {
  subnet_options = {
    app-private-a = "${lookup(module.network.subnets-app-private, "a", "")}"
    app-private-b = "${lookup(module.network.subnets-app-private, "b", "")}"
    app-private-c = "${lookup(module.network.subnets-app-private, "c", "")}"
    app-private-f = "${lookup(module.network.subnets-app-private, "f", "")}"
    db-private-a = "${lookup(module.network.subnets-db-private, "a", "")}"
    db-private-b = "${lookup(module.network.subnets-db-private, "b", "")}"
    db-private-c = "${lookup(module.network.subnets-db-private, "c", "")}"
    db-private-f = "${lookup(module.network.subnets-db-private, "f", "")}"
    public-a = "${lookup(module.network.subnets-public, "a", "")}"
    public-b = "${lookup(module.network.subnets-public, "b", "")}"
    public-c = "${lookup(module.network.subnets-public, "c", "")}"
    public-f = "${lookup(module.network.subnets-public, "f", "")}"
  }
  security_group_options = {
    "public" = ["${module.network.proxy-sg}", "${module.network.ssh-sg}", "${module.network.vpn-connections-sg}"]
    "app-private" = ["${module.network.app-private-sg}", "${module.network.ssh-sg}", "${module.network.vpn-connections-sg}"]
    "db-private" = ["${module.network.db-private-sg}", "${module.network.ssh-sg}", "${module.network.vpn-connections-sg}"]
  }
}

module "servers" {
  source = "../servers"
  servers = "${var.servers}"
  server_image = "${var.server_image}"
  environment = "${var.environment}"
  vpc_id = "${module.network.vpc-id}"
  subnet_options = "${local.subnet_options}"
  security_group_options = "${local.security_group_options}"
  key_name = "${var.key_name}"
}

module "proxy_servers" {
  source = "../servers"
  servers = "${var.proxy_servers}"
  server_image = "${var.server_image}"
  environment = "${var.environment}"
  vpc_id = "${module.network.vpc-id}"
  subnet_options = "${local.subnet_options}"
  security_group_options = "${local.security_group_options}"
  key_name = "${var.key_name}"
}

resource "aws_eip" "proxy" {
  count = "${module.proxy_servers.count}"
  vpc = true
  instance = "${module.proxy_servers.server[count.index]}"
  associate_with_private_ip = "${module.proxy_servers.server_private_ip[count.index]}"
}

module "Redis" {
  source               = "../elasticache"
  create               = "${lookup(local.redis, "create", true)}"
  cluster_id           = "redis-${var.environment}"
  engine               = "redis"
  engine_version       = "${local.redis["engine_version"]}"
  node_type            = "${local.redis["node_type"]}"
  num_cache_nodes      = "${local.redis["num_cache_nodes"]}"
  parameter_group_name = "${local.redis["parameter_group_name"]}"
  port                 = 6379
  elasticache_subnets  = "${values(module.network.subnets-db-private)}"
  security_group_ids   = ["${module.network.elasticache-sg}", "${module.network.vpn-connections-sg}"]
}

module "openvpn" {
  source = "../openvpn"
  openvpn_image = "${var.openvpn_image}"
  environment = "${var.environment}"
  vpn_size = "${var.openvpn_instance_type}"
  # hardcoded, should be configurable like the others
  instance_subnet = "${module.network.subnets-public["a"]}"
  vpc_id = "${module.network.vpc-id}"
  vpc_cidr = "${module.network.vpc-cidr}"
  key_name = "${var.key_name}"
}

module "Users" {
  source = "../iam"
  account_alias = "${var.account_alias}"
}
