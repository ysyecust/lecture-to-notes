FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      imagemagick poppler-utils qpdf pandoc \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir beautifulsoup4==4.14.3
WORKDIR /trusted
COPY scripts/pdf_inspector.py scripts/validate_contribution.py scripts/site_catalog.py scripts/build_site.py scripts/web_notes.py scripts/
ENV PYTHONPATH=/trusted
ENTRYPOINT ["python3", "-m", "scripts.validate_contribution"]
