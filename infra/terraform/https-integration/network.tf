data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  availability_zones = {
    a = sort(data.aws_availability_zones.available.names)[0]
    b = sort(data.aws_availability_zones.available.names)[1]
  }
}

resource "aws_vpc" "integration" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "governed-https-integration" }
}

resource "aws_internet_gateway" "integration" {
  vpc_id = aws_vpc.integration.id
}

resource "aws_subnet" "public" {
  for_each                = local.availability_zones
  vpc_id                  = aws_vpc.integration.id
  availability_zone       = each.value
  cidr_block              = var.public_subnet_cidrs[each.key]
  map_public_ip_on_launch = false

  tags = { Name = "governed-integration-public-${each.key}" }
}

resource "aws_subnet" "private" {
  for_each                = local.availability_zones
  vpc_id                  = aws_vpc.integration.id
  availability_zone       = each.value
  cidr_block              = var.private_subnet_cidrs[each.key]
  map_public_ip_on_launch = false

  tags = { Name = "governed-integration-private-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.integration.id
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.integration.id
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  for_each = var.enable_private_egress ? local.availability_zones : {}
  domain   = "vpc"

  tags = { Name = "governed-integration-nat-${each.key}" }
}

resource "aws_nat_gateway" "private_egress" {
  for_each      = var.enable_private_egress ? aws_subnet.public : {}
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = each.value.id

  depends_on = [aws_route.public_default]

  tags = { Name = "governed-integration-nat-${each.key}" }
}

resource "aws_route_table" "private" {
  for_each = local.availability_zones
  vpc_id   = aws_vpc.integration.id
}

resource "aws_route" "private_default" {
  for_each               = var.enable_private_egress ? aws_route_table.private : {}
  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.private_egress[each.key].id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_security_group" "gateway" {
  name_prefix = "governed-gateway-"
  description = "Future Gateway workloads; no inbound access in this foundation"
  vpc_id      = aws_vpc.integration.id
}

resource "aws_vpc_security_group_egress_rule" "gateway_https" {
  security_group_id = aws_security_group.gateway.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "gateway_state_db" {
  security_group_id            = aws_security_group.gateway.id
  referenced_security_group_id = aws_security_group.state_db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
