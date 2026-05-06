# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG TASK_VERSION=v3.44.0

USER root
RUN GOBIN=/usr/local/bin go install github.com/go-task/task/v3/cmd/task@${TASK_VERSION}
