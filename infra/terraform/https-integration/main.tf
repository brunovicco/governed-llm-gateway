resource "aws_security_group" "pdp_alb" {
  name_prefix = "governed-pdp-alb-"
  description = "Internal HTTPS PDP ingress from Gateway only"
  vpc_id      = aws_vpc.integration.id
}

resource "aws_vpc_security_group_ingress_rule" "pdp_from_gateway" {
  security_group_id            = aws_security_group.pdp_alb.id
  referenced_security_group_id = aws_security_group.gateway.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_security_group" "pdp_target" {
  name_prefix = "governed-pdp-target-"
  description = "Policy Model Router targets behind the internal ALB"
  vpc_id      = aws_vpc.integration.id
}

resource "aws_vpc_security_group_ingress_rule" "pdp_from_alb" {
  security_group_id            = aws_security_group.pdp_target.id
  referenced_security_group_id = aws_security_group.pdp_alb.id
  ip_protocol                  = "tcp"
  from_port                    = var.pdp_target_port
  to_port                      = var.pdp_target_port
}

resource "aws_vpc_security_group_egress_rule" "alb_to_pdp" {
  security_group_id            = aws_security_group.pdp_alb.id
  referenced_security_group_id = aws_security_group.pdp_target.id
  ip_protocol                  = "tcp"
  from_port                    = var.pdp_target_port
  to_port                      = var.pdp_target_port
}

resource "aws_lb" "pdp" {
  name                       = "governed-pdp-integration"
  internal                   = true
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.pdp_alb.id]
  subnets                    = [for subnet in aws_subnet.private : subnet.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = true

}

resource "aws_lb_target_group" "pdp" {
  name        = "governed-pdp-integration"
  port        = var.pdp_target_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.integration.id

  health_check {
    path                = "/readyz"
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "pdp_https" {
  load_balancer_arn = aws_lb.pdp.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.pdp.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.pdp.arn
  }
}

resource "aws_route53_record" "pdp" {
  zone_id = aws_route53_zone.private.zone_id
  name    = local.pdp_dns_name
  type    = "A"

  alias {
    name                   = aws_lb.pdp.dns_name
    zone_id                = aws_lb.pdp.zone_id
    evaluate_target_health = true
  }
}

resource "aws_security_group" "state_db" {
  name_prefix = "governed-state-db-"
  description = "Private durable state for future credential and spend controls"
  vpc_id      = aws_vpc.integration.id
}

resource "aws_vpc_security_group_ingress_rule" "state_db_from_gateway" {
  security_group_id            = aws_security_group.state_db.id
  referenced_security_group_id = aws_security_group.gateway.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_subnet_group" "state" {
  name_prefix = "governed-state-"
  subnet_ids  = [for subnet in aws_subnet.private : subnet.id]
}

resource "aws_db_parameter_group" "state" {
  name_prefix = "governed-state-postgres17-"
  family      = "postgres17"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "state" {
  identifier                  = "governed-state-integration"
  engine                      = "postgres"
  engine_version              = var.database_engine_version
  instance_class              = var.database_instance_class
  allocated_storage           = var.database_allocated_storage_gib
  storage_type                = "gp3"
  storage_encrypted           = true
  multi_az                    = true
  publicly_accessible         = false
  db_subnet_group_name        = aws_db_subnet_group.state.name
  parameter_group_name        = aws_db_parameter_group.state.name
  vpc_security_group_ids      = [aws_security_group.state_db.id]
  username                    = "governed_admin"
  manage_master_user_password = true
  backup_retention_period     = 7
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "governed-state-integration-final"
  copy_tags_to_snapshot       = true
  auto_minor_version_upgrade  = false

}

resource "aws_secretsmanager_secret" "provider_credential" {
  for_each                = var.provider_credential_names
  name                    = each.value
  description             = "Provider credential container; value and version published outside Terraform"
  recovery_window_in_days = 30
}
