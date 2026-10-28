"""Every public API operation, and the SDK method that calls it.

This table is hand-maintained and is the one place SDK method names are
chosen. ``scripts/generate_resources.py`` reads it to write the resource
classes, and ``tests/test_spec_coverage.py`` fails when an operation in
``openapi/public-api.yaml`` is missing here (or from ``NOT_IN_SDK``) or
points at the wrong route.

Each entry is ``operationId: (HTTP method, path under /public/v1, method)``,
where *method* is the attribute path from the client, for example
``"networks.subnets.list"`` for ``client.networks.subnets.list(...)``.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

OPERATIONS: Dict[str, Tuple[str, str, str]] = {
    # Account
    "getMe": ("GET", "/me", "me.get"),
    "revokeMe": ("DELETE", "/me", "me.revoke"),
    # Billing
    "getCredit": ("GET", "/billing/credit", "billing.get_credit"),
    "createCreditPurchase": ("POST", "/billing/credit/purchases", "billing.create_credit_purchase"),
    "getCreditPurchase": ("GET", "/billing/credit/purchases/{purchase_id}", "billing.get_credit_purchase"),
    "listReceipts": ("GET", "/billing/receipts", "billing.receipts.list"),
    "getReceipt": ("GET", "/billing/receipts/{receipt_id}", "billing.receipts.get"),
    "getReceiptPdf": ("GET", "/billing/receipts/{receipt_id}/pdf", "billing.receipts.get_pdf"),
    # Usage
    "getUsage": ("GET", "/usage", "usage.get"),
    "getUsageByResource": ("GET", "/usage/by-resource", "usage.get_by_resource"),
    # Catalogue
    "listRegions": ("GET", "/regions", "catalog.list_regions"),
    "listPlans": ("GET", "/plans", "catalog.list_plans"),
    "listImages": ("GET", "/images", "catalog.list_images"),
    "listDiskOfferings": ("GET", "/disk-offerings", "catalog.list_disk_offerings"),
    "quoteDiskOffering": ("GET", "/disk-offerings/{slug}/quote", "catalog.quote_disk_offering"),
    "listDatabaseEngines": ("GET", "/database-engines", "catalog.list_database_engines"),
    "listKubernetesVersions": ("GET", "/kubernetes-versions", "catalog.list_kubernetes_versions"),
    "estimatePricing": ("POST", "/pricing/estimate", "catalog.estimate_price"),
    # Instances
    "listInstances": ("GET", "/instances", "instances.list"),
    "createInstance": ("POST", "/instances", "instances.create"),
    "getInstance": ("GET", "/instances/{instance_id}", "instances.get"),
    "deleteInstance": ("DELETE", "/instances/{instance_id}", "instances.delete"),
    "startInstance": ("POST", "/instances/{instance_id}/start", "instances.start"),
    "stopInstance": ("POST", "/instances/{instance_id}/stop", "instances.stop"),
    "rebootInstance": ("POST", "/instances/{instance_id}/reboot", "instances.reboot"),
    "rebuildInstance": ("POST", "/instances/{instance_id}/rebuild", "instances.rebuild"),
    "renameInstance": ("POST", "/instances/{instance_id}/rename", "instances.rename"),
    "resizeInstance": ("POST", "/instances/{instance_id}/resize", "instances.resize"),
    "restoreInstance": ("POST", "/instances/{instance_id}/restore", "instances.restore"),
    "changeInstanceSSHKey": ("POST", "/instances/{instance_id}/change-ssh-key", "instances.change_ssh_key"),
    "changeInstanceSecurityGroup": (
        "PUT",
        "/instances/{instance_id}/security-group",
        "instances.change_security_group",
    ),
    "attachInstancePrivateNetwork": (
        "POST",
        "/instances/{instance_id}/private-network",
        "instances.attach_private_network",
    ),
    "detachInstancePrivateNetwork": (
        "DELETE",
        "/instances/{instance_id}/private-network",
        "instances.detach_private_network",
    ),
    "openInstanceConsole": ("POST", "/instances/{instance_id}/console", "instances.open_console"),
    "issueVolumeKeyCredential": (
        "POST",
        "/instances/{instance_id}/volume-key-credential",
        "instances.issue_volume_key_credential",
    ),
    "getInstanceMetrics": ("GET", "/instances/{instance_id}/metrics", "instances.get_metrics"),
    "getInstanceUsage": ("GET", "/instances/{instance_id}/usage", "instances.get_usage"),
    "listInstanceVolumes": ("GET", "/instances/{instance_id}/volumes", "instances.list_volumes"),
    "listInstanceSnapshots": ("GET", "/instances/{instance_id}/snapshots", "instances.list_snapshots"),
    "createInstanceSnapshot": ("POST", "/instances/{instance_id}/snapshots", "instances.create_snapshot"),
    "getInstanceSnapshotSchedule": (
        "GET",
        "/instances/{instance_id}/snapshot-schedule",
        "instances.get_snapshot_schedule",
    ),
    "putInstanceSnapshotSchedule": (
        "PUT",
        "/instances/{instance_id}/snapshot-schedule",
        "instances.set_snapshot_schedule",
    ),
    "openSSHAccess": ("POST", "/instances/{instance_id}/ssh-access", "instances.ssh_access.open"),
    "getSSHAccess": ("GET", "/instances/{instance_id}/ssh-access/{grant_id}", "instances.ssh_access.get"),
    "revokeSSHAccess": (
        "DELETE",
        "/instances/{instance_id}/ssh-access/{grant_id}",
        "instances.ssh_access.revoke",
    ),
    "listInstanceOrders": ("GET", "/instance-orders", "instances.orders.list"),
    "getInstanceOrder": ("GET", "/instance-orders/{order_id}", "instances.orders.get"),
    # Networks, subnets and firewall rules
    "listNetworks": ("GET", "/networks", "networks.list"),
    "createNetwork": ("POST", "/networks", "networks.create"),
    "quoteNetwork": ("GET", "/networks/quote", "networks.quote"),
    "getNetwork": ("GET", "/networks/{network_id}", "networks.get"),
    "deleteNetwork": ("DELETE", "/networks/{network_id}", "networks.delete"),
    "listSubnets": ("GET", "/networks/{network_id}/subnets", "networks.subnets.list"),
    "createSubnet": ("POST", "/networks/{network_id}/subnets", "networks.subnets.create"),
    "getSubnet": ("GET", "/subnets/{subnet_id}", "networks.subnets.get"),
    "deleteSubnet": ("DELETE", "/subnets/{subnet_id}", "networks.subnets.delete"),
    "listFirewallRules": ("GET", "/subnets/{subnet_id}/firewall-rules", "networks.firewall_rules.list"),
    "createFirewallRule": ("POST", "/subnets/{subnet_id}/firewall-rules", "networks.firewall_rules.create"),
    "getFirewallRule": (
        "GET",
        "/subnets/{subnet_id}/firewall-rules/{rule_id}",
        "networks.firewall_rules.get",
    ),
    "deleteFirewallRule": ("DELETE", "/firewall-rules/{rule_id}", "networks.firewall_rules.delete"),
    # Public IPs and port forwarding
    "listPublicIPs": ("GET", "/public-ips", "public_ips.list"),
    "createPublicIP": ("POST", "/public-ips", "public_ips.create"),
    "quotePublicIP": ("GET", "/public-ips/quote", "public_ips.quote"),
    "getPublicIP": ("GET", "/public-ips/{public_ip_id}", "public_ips.get"),
    "deletePublicIP": ("DELETE", "/public-ips/{public_ip_id}", "public_ips.delete"),
    "attachPublicIP": ("POST", "/public-ips/{public_ip_id}/attach", "public_ips.attach"),
    "detachPublicIP": ("POST", "/public-ips/{public_ip_id}/detach", "public_ips.detach"),
    "listPortForwardingRules": (
        "GET",
        "/public-ips/{public_ip_id}/port-forwarding-rules",
        "public_ips.port_forwarding_rules.list",
    ),
    "createPortForwardingRule": (
        "POST",
        "/public-ips/{public_ip_id}/port-forwarding-rules",
        "public_ips.port_forwarding_rules.create",
    ),
    "getPortForwardingRule": (
        "GET",
        "/public-ips/{public_ip_id}/port-forwarding-rules/{rule_id}",
        "public_ips.port_forwarding_rules.get",
    ),
    "deletePortForwardingRule": (
        "DELETE",
        "/port-forwarding-rules/{rule_id}",
        "public_ips.port_forwarding_rules.delete",
    ),
    # Load balancers
    "listLoadBalancers": ("GET", "/load-balancers", "load_balancers.list"),
    "createLoadBalancer": ("POST", "/load-balancers", "load_balancers.create"),
    "getLoadBalancer": ("GET", "/load-balancers/{load_balancer_id}", "load_balancers.get"),
    "updateLoadBalancer": ("PATCH", "/load-balancers/{load_balancer_id}", "load_balancers.update"),
    "deleteLoadBalancer": ("DELETE", "/load-balancers/{load_balancer_id}", "load_balancers.delete"),
    # Security groups
    "listSecurityGroups": ("GET", "/security-groups", "security_groups.list"),
    "createSecurityGroup": ("POST", "/security-groups", "security_groups.create"),
    "getSecurityGroup": ("GET", "/security-groups/{security_group_id}", "security_groups.get"),
    "deleteSecurityGroup": ("DELETE", "/security-groups/{security_group_id}", "security_groups.delete"),
    "replaceSecurityGroupRules": (
        "PUT",
        "/security-groups/{security_group_id}/rules",
        "security_groups.replace_rules",
    ),
    # Volumes
    "listVolumes": ("GET", "/volumes", "volumes.list"),
    "createVolume": ("POST", "/volumes", "volumes.create"),
    "getVolume": ("GET", "/volumes/{volume_id}", "volumes.get"),
    "deleteVolume": ("DELETE", "/volumes/{volume_id}", "volumes.delete"),
    "attachVolume": ("POST", "/volumes/{volume_id}/attach", "volumes.attach"),
    "detachVolume": ("POST", "/volumes/{volume_id}/detach", "volumes.detach"),
    "resizeVolume": ("POST", "/volumes/{volume_id}/resize", "volumes.resize"),
    "getVolumeUsage": ("GET", "/volumes/{volume_id}/usage", "volumes.get_usage"),
    "listVolumeSnapshots": ("GET", "/volumes/{volume_id}/snapshots", "volumes.list_snapshots"),
    "createVolumeSnapshot": ("POST", "/volumes/{volume_id}/snapshots", "volumes.create_snapshot"),
    "getVolumeSnapshotSchedule": (
        "GET",
        "/volumes/{volume_id}/snapshot-schedule",
        "volumes.get_snapshot_schedule",
    ),
    "putVolumeSnapshotSchedule": (
        "PUT",
        "/volumes/{volume_id}/snapshot-schedule",
        "volumes.set_snapshot_schedule",
    ),
    # Snapshots
    "listSnapshots": ("GET", "/snapshots", "snapshots.list"),
    "quoteSnapshot": ("GET", "/snapshots/quote", "snapshots.quote"),
    "getSnapshot": ("GET", "/snapshots/{snapshot_id}", "snapshots.get"),
    "deleteSnapshot": ("DELETE", "/snapshots/{snapshot_id}", "snapshots.delete"),
    "restoreSnapshot": ("POST", "/snapshots/{snapshot_id}/restore", "snapshots.restore"),
    "getSnapshotUsage": ("GET", "/snapshots/{snapshot_id}/usage", "snapshots.get_usage"),
    # Databases
    "listDatabases": ("GET", "/databases", "databases.list"),
    "createDatabase": ("POST", "/databases", "databases.create"),
    "getDatabase": ("GET", "/databases/{database_id}", "databases.get"),
    "deleteDatabase": ("DELETE", "/databases/{database_id}", "databases.delete"),
    "startDatabase": ("POST", "/databases/{database_id}/start", "databases.start"),
    "stopDatabase": ("POST", "/databases/{database_id}/stop", "databases.stop"),
    "replaceDatabaseAccessRules": (
        "PUT",
        "/databases/{database_id}/access-rules",
        "databases.replace_access_rules",
    ),
    "setDatabaseSecurityGroups": (
        "PUT",
        "/databases/{database_id}/security-groups",
        "databases.set_security_groups",
    ),
    "changeDatabasePassword": ("PUT", "/databases/{database_id}/password", "databases.change_password"),
    "resetDatabasePassword": ("POST", "/databases/{database_id}/reset-password", "databases.reset_password"),
    "resizeDatabaseStorage": ("POST", "/databases/{database_id}/resize-storage", "databases.resize_storage"),
    "listDatabaseSnapshots": ("GET", "/databases/{database_id}/snapshots", "databases.snapshots.list"),
    "createDatabaseSnapshot": ("POST", "/databases/{database_id}/snapshots", "databases.snapshots.create"),
    "getDatabaseSnapshot": (
        "GET",
        "/databases/{database_id}/snapshots/{snapshot_id}",
        "databases.snapshots.get",
    ),
    "deleteDatabaseSnapshot": (
        "DELETE",
        "/databases/{database_id}/snapshots/{snapshot_id}",
        "databases.snapshots.delete",
    ),
    "listDatabaseOrders": ("GET", "/database-orders", "databases.orders.list"),
    "getDatabaseOrder": ("GET", "/database-orders/{order_id}", "databases.orders.get"),
    # Kubernetes
    "listKubernetesClusters": ("GET", "/kubernetes-clusters", "kubernetes.list"),
    "createKubernetesCluster": ("POST", "/kubernetes-clusters", "kubernetes.create"),
    "getKubernetesCluster": ("GET", "/kubernetes-clusters/{cluster_id}", "kubernetes.get"),
    "scaleKubernetesCluster": ("PATCH", "/kubernetes-clusters/{cluster_id}", "kubernetes.scale"),
    "deleteKubernetesCluster": ("DELETE", "/kubernetes-clusters/{cluster_id}", "kubernetes.delete"),
    "upgradeKubernetesCluster": ("POST", "/kubernetes-clusters/{cluster_id}/upgrade", "kubernetes.upgrade"),
    "resizeKubernetesClusterPlan": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/resize-plan",
        "kubernetes.resize_plan",
    ),
    "upgradeKubernetesClusterNetwork": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/upgrade-network",
        "kubernetes.upgrade_network",
    ),
    "configureKubernetesEndpointAccess": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/endpoint-access",
        "kubernetes.configure_endpoint_access",
    ),
    "startKubernetesCluster": ("POST", "/kubernetes-clusters/{cluster_id}/start", "kubernetes.start"),
    "stopKubernetesCluster": ("POST", "/kubernetes-clusters/{cluster_id}/stop", "kubernetes.stop"),
    "getKubernetesKubeconfig": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/kubeconfig",
        "kubernetes.get_kubeconfig",
    ),
    "listKubernetesClusterNodes": ("GET", "/kubernetes-clusters/{cluster_id}/nodes", "kubernetes.list_nodes"),
    "getKubernetesWorkloads": ("GET", "/kubernetes-clusters/{cluster_id}/workloads", "kubernetes.get_workloads"),
    "applyKubernetesManifest": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/apply-manifest",
        "kubernetes.apply_manifest",
    ),
    "getKubernetesLiveManifests": (
        "GET",
        "/kubernetes-clusters/{cluster_id}/live-manifests",
        "kubernetes.get_live_manifests",
    ),
    "exposeKubernetesService": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/expose-service",
        "kubernetes.expose_service",
    ),
    "syncKubernetesRouting": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/sync-routing",
        "kubernetes.sync_routing",
    ),
    "listKubernetesNodePools": (
        "GET",
        "/kubernetes-clusters/{cluster_id}/node-pools",
        "kubernetes.node_pools.list",
    ),
    "createKubernetesNodePool": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/node-pools",
        "kubernetes.node_pools.create",
    ),
    "scaleKubernetesNodePool": (
        "PATCH",
        "/kubernetes-clusters/{cluster_id}/node-pools/{pool_id}",
        "kubernetes.node_pools.scale",
    ),
    "deleteKubernetesNodePool": (
        "DELETE",
        "/kubernetes-clusters/{cluster_id}/node-pools/{pool_id}",
        "kubernetes.node_pools.delete",
    ),
    "listKubernetesAddons": ("GET", "/kubernetes-clusters/{cluster_id}/addons", "kubernetes.addons.list"),
    "toggleKubernetesAddon": (
        "POST",
        "/kubernetes-clusters/{cluster_id}/addons/{addon_name}/toggle",
        "kubernetes.addons.toggle",
    ),
    # SSH keys
    "listSSHKeys": ("GET", "/ssh-keys", "ssh_keys.list"),
    "createSSHKey": ("POST", "/ssh-keys", "ssh_keys.create"),
    "getSSHKey": ("GET", "/ssh-keys/{ssh_key_id}", "ssh_keys.get"),
    "deleteSSHKey": ("DELETE", "/ssh-keys/{ssh_key_id}", "ssh_keys.delete"),
    # Webhooks
    "listWebhookEventTypes": ("GET", "/webhook-event-types", "webhooks.list_event_types"),
    "listWebhooks": ("GET", "/webhooks", "webhooks.list"),
    "createWebhook": ("POST", "/webhooks", "webhooks.create"),
    "getWebhook": ("GET", "/webhooks/{webhook_id}", "webhooks.get"),
    "updateWebhook": ("PATCH", "/webhooks/{webhook_id}", "webhooks.update"),
    "deleteWebhook": ("DELETE", "/webhooks/{webhook_id}", "webhooks.delete"),
    "testWebhook": ("POST", "/webhooks/{webhook_id}/test", "webhooks.test"),
    "rotateWebhookSecret": ("POST", "/webhooks/{webhook_id}/rotate-secret", "webhooks.rotate_secret"),
    "listWebhookDeliveries": ("GET", "/webhooks/{webhook_id}/deliveries", "webhooks.deliveries.list"),
    "getWebhookDelivery": (
        "GET",
        "/webhooks/{webhook_id}/deliveries/{delivery_id}",
        "webhooks.deliveries.get",
    ),
    "redeliverWebhook": (
        "POST",
        "/webhooks/{webhook_id}/deliveries/{delivery_id}/redeliver",
        "webhooks.deliveries.redeliver",
    ),
    # Migrate
    "listCloudConnections": ("GET", "/cloud-connections", "migrate.connections.list"),
    "createCloudConnection": ("POST", "/cloud-connections", "migrate.connections.create"),
    "getCloudConnection": ("GET", "/cloud-connections/{connection_id}", "migrate.connections.get"),
    "updateCloudConnection": ("PATCH", "/cloud-connections/{connection_id}", "migrate.connections.update"),
    "deleteCloudConnection": ("DELETE", "/cloud-connections/{connection_id}", "migrate.connections.delete"),
    "listCloudScans": ("GET", "/cloud-connections/{connection_id}/scans", "migrate.scans.list"),
    "startCloudScan": ("POST", "/cloud-connections/{connection_id}/scans", "migrate.scans.start"),
    "getCloudScan": ("GET", "/cloud-scans/{scan_id}", "migrate.scans.get"),
    "listMigrations": ("GET", "/migrations", "migrate.migrations.list"),
    "createMigration": ("POST", "/migrations", "migrate.migrations.create"),
    "getMigration": ("GET", "/migrations/{migration_id}", "migrate.migrations.get"),
    "renameMigration": ("PATCH", "/migrations/{migration_id}", "migrate.migrations.rename"),
    "deleteMigration": ("DELETE", "/migrations/{migration_id}", "migrate.migrations.delete"),
    "updateMigrationItem": ("PATCH", "/migrations/{migration_id}/items", "migrate.migrations.update_item"),
    "exportMigrationTerraform": (
        "GET",
        "/migrations/{migration_id}/terraform",
        "migrate.migrations.export_terraform",
    ),
    # Operations
    "getOperation": ("GET", "/operations/{operation_id}", "operations.get"),
    "streamOperation": ("GET", "/operations/{operation_id}/events", "operations.stream"),
}

# Writes the API does not replay on a repeated Idempotency-Key: a retry would
# repeat the change (send another test event, rotate again) or fail on the
# first attempt's result. The SDK sends these once, retrying only a 429, which
# the API refuses before doing anything. DELETE /me is here because a retry
# after a lost response would fail with 401: the key is already gone.
NO_REPLAY: FrozenSet[str] = frozenset(
    {
        "createSSHKey",
        "deleteSSHKey",
        "openInstanceConsole",
        "issueVolumeKeyCredential",
        "testWebhook",
        "deleteWebhook",
        "rotateWebhookSecret",
        "redeliverWebhook",
        "revokeMe",
    }
)

# Spec operations the SDK deliberately has no method for yet, with the reason.
# The generators skip them (and the schemas only they use), and the coverage
# test accepts them. Agent sessions answer only AI apps connected through
# Pantech's MCP server; a standard API key gets 403
# AGENT_SESSIONS_NOT_FOR_API_KEYS. Remove an entry when its method is added.
_AGENT_SESSIONS = "agent sessions: MCP-connected AI apps only"
NOT_IN_SDK: Dict[str, str] = {
    "getInstanceAgent": _AGENT_SESSIONS,
    "startAgentSession": _AGENT_SESSIONS,
    "listAgentSessions": _AGENT_SESSIONS,
    "getAgentSession": _AGENT_SESSIONS,
    "messageAgentSession": _AGENT_SESSIONS,
    "callAgentTool": _AGENT_SESSIONS,
    "getAgentToolCall": _AGENT_SESSIONS,
    "listAgentSessionEvents": _AGENT_SESSIONS,
    "decideAgentApproval": _AGENT_SESSIONS,
    "terminateAgentSession": _AGENT_SESSIONS,
    "getAgentSessionReport": _AGENT_SESSIONS,
}
