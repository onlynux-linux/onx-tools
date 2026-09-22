FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make binutils libc6-dev bash grep sed gawk diffutils findutils \
    xz-utils tar gzip bzip2 ca-certificates python3 python3-pip \
    meson ninja-build pkg-config libssl-dev zlib1g-dev libzstd-dev \
    git cmake perl patch && rm -rf /var/lib/apt/lists/*
COPY tatami /tatami
RUN meson setup /tatami/build /tatami --prefix=/usr/local --default-library=static \
    -Ddocs=disabled -Dhelp=disabled -Dlua=disabled -Dpython=disabled -Dtests=disabled \
    && meson compile -C /tatami/build && meson install -C /tatami/build
COPY onx /opt/onx/onx
COPY ci/bootstrap.py /tmp/bootstrap.py
RUN python3 /tmp/bootstrap.py
ENV PYTHONPATH=/opt/onx ONX_BUILD_CONTAINER=1
