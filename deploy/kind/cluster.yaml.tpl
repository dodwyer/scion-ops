kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: __HUB_NODE_PORT__
        hostPort: __HUB_HOST_PORT__
        listenAddress: "__KIND_LISTEN_ADDRESS__"
        protocol: TCP
      - containerPort: __MCP_NODE_PORT__
        hostPort: __MCP_HOST_PORT__
        listenAddress: "__KIND_LISTEN_ADDRESS__"
        protocol: TCP
    extraMounts:
      - hostPath: "__WORKSPACE_HOST_PATH__"
        containerPath: "__WORKSPACE_NODE_PATH__"
