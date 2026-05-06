set -eu

credential_name="${SCION_BROKER_CREDENTIAL_NAME:-in-cluster}"
broker_port="${SCION_BROKER_PORT:-9800}"
secret_credential_file="/run/secrets/scion-broker-credentials/${credential_name}.json"
credential_dir="${HOME}/.scion/hub-credentials"
credential_file="${credential_dir}/${credential_name}.json"

mkdir -p "${HOME}/.scion" "${credential_dir}"

if [ -f "${secret_credential_file}" ]; then
  cp "${secret_credential_file}" "${credential_file}"
  chmod 0700 "${credential_dir}"
  chmod 0600 "${credential_file}"
  exec scion --global server start \
    --foreground \
    --production \
    --enable-runtime-broker \
    --runtime-broker-port "${broker_port}"
fi

bootstrap_home="${SCION_BROKER_BOOTSTRAP_HOME:-/tmp/scion-broker-bootstrap}"
mkdir -p "${bootstrap_home}/.scion"
cp /etc/scion/broker-bootstrap-settings.yaml "${bootstrap_home}/.scion/settings.yaml"

exec env HOME="${bootstrap_home}" scion --global server start \
  --foreground \
  --production \
  --enable-runtime-broker \
  --config /etc/scion/broker-bootstrap-server.yaml \
  --runtime-broker-port "${broker_port}"
