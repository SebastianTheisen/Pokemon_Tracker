# syntax=docker/dockerfile:1
# Build-Umgebung für die Flutter-App „Kartenkiste“: Web (PWA) und Android-APK.
# Wird nur zum Bauen gestartet (docker compose --profile build run --rm app-builder ...).
FROM ubuntu:24.04

ARG FLUTTER_VERSION=3.47.7
ARG ANDROID_PLATFORM=android-36
ARG ANDROID_BUILD_TOOLS=36.0.0

ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    PUB_CACHE=/cache/pub \
    GRADLE_USER_HOME=/cache/gradle
ENV PATH="/opt/flutter/bin:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl git unzip xz-utils zip openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Flutter-SDK (feste Version wie in der Entwicklung)
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    | tar -xJ -C /opt \
    && git config --global --add safe.directory /opt/flutter \
    && flutter config --no-analytics --no-cli-animations >/dev/null

# Android-SDK: aktuelle Kommandozeilen-Tools aus dem offiziellen Verzeichnis ermitteln
RUN set -eux; \
    tools="$(curl -fsSL https://dl.google.com/android/repository/repository2-3.xml \
      | grep -o 'commandlinetools-linux-[0-9]*_latest.zip' | sort -V | tail -1)"; \
    mkdir -p "${ANDROID_HOME}/cmdline-tools"; \
    curl -fsSL -o /tmp/tools.zip "https://dl.google.com/android/repository/${tools}"; \
    unzip -q /tmp/tools.zip -d "${ANDROID_HOME}/cmdline-tools"; \
    mv "${ANDROID_HOME}/cmdline-tools/cmdline-tools" "${ANDROID_HOME}/cmdline-tools/latest"; \
    rm /tmp/tools.zip; \
    yes | sdkmanager --licenses >/dev/null; \
    sdkmanager --install "platform-tools" "platforms;${ANDROID_PLATFORM}" "build-tools;${ANDROID_BUILD_TOOLS}" >/dev/null

RUN flutter precache --android --web >/dev/null && flutter doctor -v | head -40

WORKDIR /work
