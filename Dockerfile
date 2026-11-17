# Svartsengi InSAR pipeline: Linux toolchain (micromamba env + LiCSBAS + make)
FROM mambaorg/micromamba:1.5.10

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends git make ca-certificates wget \
 && rm -rf /var/lib/apt/lists/*

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml \
 && micromamba clean --all --yes

# Maintained COMET fork (NOT yumorishita/LiCSBAS, whose URLs broke in Oct 2025).
# Pinned for reproducibility; bump deliberately.
ARG LICSBAS_REF=a145e6c4217b29eb7348ea95630454a099809098
RUN git clone https://github.com/comet-licsar/LiCSBAS /opt/LiCSBAS \
 && git -C /opt/LiCSBAS checkout "$LICSBAS_REF" \
 && chmod +x /opt/LiCSBAS/bin/*

# Memory-layout patch for step 12 (see docker/patch_licsbas.sh); results unchanged
COPY docker/patch_licsbas.sh /tmp/patch_licsbas.sh
RUN bash /tmp/patch_licsbas.sh

# Resumable step 13 with small patches, no patches past the last row (see docker/patch_licsbas13.py)
COPY docker/patch_licsbas13.py /tmp/patch_licsbas13.py
RUN /opt/conda/bin/python /tmp/patch_licsbas13.py

ENV LICSBAS_DIR=/opt/LiCSBAS \
    PATH=/opt/LiCSBAS/bin:$PATH \
    PYTHONPATH=/opt/LiCSBAS/LiCSBAS_lib

# LiCSBAS work dir; a new named volume mounted here inherits this ownership
RUN mkdir -p /vol && chown $MAMBA_USER:$MAMBA_USER /vol

WORKDIR /work
USER $MAMBA_USER
CMD ["make", "help"]
