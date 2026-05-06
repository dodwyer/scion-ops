# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG GEMINI_CLI_VERSION=0.11.3

RUN npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION} \
  && npm cache clean --force

CMD ["gemini"]
