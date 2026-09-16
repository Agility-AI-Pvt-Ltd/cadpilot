# FreeCAD is built from the official source repository, not a third-party image.
# Pin FREECAD_REF to an immutable commit SHA in production. `main` is useful only
# for development and CI experiments because it is not reproducible.
FROM ubuntu:24.04

ARG FREECAD_REF=main
ARG FREECAD_BUILD_JOBS=2
ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/root/.pixi/bin:${PATH} \
    FREECAD_HOME=/opt/freecad \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3-pip tini \
    libegl1 libgl1 libglu1-mesa libx11-6 libxext6 libxrender1 libxt6 \
    && rm -rf /var/lib/apt/lists/*

# Pixi is FreeCAD's documented self-contained dependency/build environment.
RUN curl -fsSL https://pixi.sh/install.sh | bash

WORKDIR ${FREECAD_HOME}
RUN git clone --filter=blob:none https://github.com/FreeCAD/FreeCAD.git . \
    && git checkout "${FREECAD_REF}" \
    && git submodule update --init --recursive \
    && pixi install \
    && pixi run configure-release \
    && pixi run cmake --build build/release --parallel "${FREECAD_BUILD_JOBS}" \
    && ln -s ${FREECAD_HOME}/build/release/bin/FreeCADCmd /usr/local/bin/freecadcmd \
    && freecadcmd -c "import FreeCAD; print(FreeCAD.Version())"

WORKDIR /app
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
RUN python3 -m pip install --break-system-packages --no-cache-dir . uv
COPY worker/entrypoint.sh /entrypoint.sh
RUN chmod 0555 /entrypoint.sh

# One FreeCAD process per container: no browser/X server is needed for freecadcmd.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD freecadcmd -c "import FreeCAD; print(FreeCAD.Version())" || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
