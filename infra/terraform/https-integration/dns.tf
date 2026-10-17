locals {
  public_zone_name  = "viccolabs.com.br"
  private_zone_name = "internal.viccolabs.com.br"
  pdp_dns_name      = "pdp.internal.viccolabs.com.br"
}

data "aws_route53_zone" "public" {
  name         = local.public_zone_name
  private_zone = false
}

resource "aws_route53_zone" "private" {
  name = local.private_zone_name

  vpc {
    vpc_id = aws_vpc.integration.id
  }
}

resource "aws_acm_certificate" "pdp" {
  domain_name       = local.pdp_dns_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "pdp_certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.pdp.domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  zone_id = data.aws_route53_zone.public.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "pdp" {
  certificate_arn         = aws_acm_certificate.pdp.arn
  validation_record_fqdns = [for record in aws_route53_record.pdp_certificate_validation : record.fqdn]
}
