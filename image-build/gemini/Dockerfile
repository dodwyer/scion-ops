# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG GEMINI_CLI_VERSION=0.11.3
ARG TASK_VERSION=v3.44.0

RUN GOBIN=/usr/local/bin go install github.com/go-task/task/v3/cmd/task@${TASK_VERSION} \
  && npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION} \
  && npm cache clean --force

CMD ["gemini"]
