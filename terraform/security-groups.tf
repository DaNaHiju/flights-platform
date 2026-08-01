# ── Security Groups ──────────────────────────────────────────────────────────
# Explicit, self-documented security groups for the EKS control plane and the
# worker nodes. All intra-cluster access is scoped via SG-to-SG references
# (source_security_group_id), never via cidr_blocks, so that traffic is
# restricted to the specific resources that need it rather than the whole VPC.

resource "aws_security_group" "cluster" {
  name_prefix = "${local.name_prefix}-cluster-"
  description = "EKS control plane security group"
  vpc_id      = aws_vpc.main.id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-cluster-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "nodes" {
  name_prefix = "${local.name_prefix}-nodes-"
  description = "EKS worker nodes security group"
  vpc_id      = aws_vpc.main.id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-nodes-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

# ── Ingress: nodes to cluster ─────────────────────────────────────────────────

resource "aws_security_group_rule" "nodes_to_cluster_https" {
  description = "Worker nodes reach the Kubernetes API server (kubelet to control plane)"
  type        = "ingress"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"

  security_group_id        = aws_security_group.cluster.id
  source_security_group_id = aws_security_group.nodes.id
}

# ── Ingress: cluster to nodes ─────────────────────────────────────────────────

resource "aws_security_group_rule" "cluster_to_nodes_kubelet" {
  description = "Control plane reaches the kubelet API on worker nodes"
  type        = "ingress"
  from_port   = 10250
  to_port     = 10250
  protocol    = "tcp"

  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.cluster.id
}

resource "aws_security_group_rule" "cluster_to_nodes_https" {
  description = "Control plane reaches node-hosted webhooks and extension API servers"
  type        = "ingress"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"

  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.cluster.id
}

resource "aws_security_group_rule" "cluster_to_nodes_ephemeral" {
  description = "Control plane reaches pods on high ports (webhooks, extension APIs on dynamic ports)"
  type        = "ingress"
  from_port   = 1025
  to_port     = 65535
  protocol    = "tcp"

  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.cluster.id
}

# ── Ingress: nodes to nodes (self-referencing) ────────────────────────────────

resource "aws_security_group_rule" "nodes_self_all" {
  description = "Pod-to-pod traffic across worker nodes (CNI, DNS, service mesh, etc.)"
  type        = "ingress"
  from_port   = 0
  to_port     = 0
  protocol    = "-1"

  security_group_id = aws_security_group.nodes.id
  self              = true
}

# ── Egress ─────────────────────────────────────────────────────────────────────
# Outbound is intentionally left open (0.0.0.0/0): this is the one place a CIDR
# block is acceptable, since egress traffic (pulling images, calling AWS APIs,
# etc.) has no fixed, enumerable destination security group to scope to.

resource "aws_security_group_rule" "cluster_egress_all" {
  description = "Allow all outbound traffic from the control plane (intentional use of CIDR)"
  type        = "egress"
  from_port   = 0
  to_port     = 0
  protocol    = "-1"
  cidr_blocks = ["0.0.0.0/0"]

  security_group_id = aws_security_group.cluster.id
}

resource "aws_security_group_rule" "nodes_egress_all" {
  description = "Allow all outbound traffic from worker nodes (intentional use of CIDR)"
  type        = "egress"
  from_port   = 0
  to_port     = 0
  protocol    = "-1"
  cidr_blocks = ["0.0.0.0/0"]

  security_group_id = aws_security_group.nodes.id
}

