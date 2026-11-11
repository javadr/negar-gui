FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqt6gui6 \
    libqt6widgets6 \
    libqt6core6 \
    libqt6network6 \
    libqt6dbus6 \
    qt6-wayland \
    libwayland-egl1 \
    libgl1-mesa-glx \
    libegl1-mesa \
    libxkbcommon-x11-0 \
    libfontconfig1 \
    libfreetype6 \
    libx11-6 \
    libxcb-cursor0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxcb-xinput0 \
    libxcb-util1 \
    libxrender1 \
    libxi6 \
    libsm6 \
    wl-clipboard \
    xclip \
    && rm -rf /var/lib/apt/lists/*

# Install from the local source, not PyPI: any change to the files invalidates this layer, so a rebuild
# always contains the current code (a PyPI install was a cached layer that kept serving an old release).
COPY . /src
RUN pip install --no-cache-dir /src typing_extensions && rm -rf /src

RUN adduser --disabled-password --gecos "" negar && \
    mkdir -p /home/negar/.config && \
    chown -R negar:negar /home/negar/.config

USER negar

ENTRYPOINT ["negar-gui"]
