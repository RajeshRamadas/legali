FROM postgres:16-bookworm
# PostgreSQL clients come from the base image; other runtime tools use Debian repositories.
RUN rm -f /etc/apt/sources.list.d/pgdg.list /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update && apt-get install -y --no-install-recommends python3 python3-boto3 gnupg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/recovery
COPY --chmod=0444 backup.py ./backup.py
USER 1000:1000
ENTRYPOINT ["python3", "/opt/recovery/backup.py"]
CMD ["--help"]
