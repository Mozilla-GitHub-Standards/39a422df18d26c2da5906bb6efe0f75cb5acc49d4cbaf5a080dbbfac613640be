FROM python:3.7-slim-stretch

ARG DEVELOPMENT=false
ENV LANG=C.UTF-8
EXPOSE 8000
CMD ["./bin/run-prod.sh"]

RUN adduser --uid 1000 --disabled-password --gecos '' --no-create-home webdev

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential mariadb-client libmariadbclient-dev \
                                               libxslt1.1 libxml2 libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# First copy requirements.txt and pip so we can take advantage of
# docker caching.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes --no-cache-dir -r requirements.txt
RUN /bin/bash -c 'if ${DEVELOPMENT}; then pip install -r requirements-dev.txt; fi'

COPY . /app
RUN DEBUG=False SECRET_KEY=foo ALLOWED_HOSTS=localhost, DATABASE_URL=sqlite:/// SITE_URL= ./manage.py collectstatic --noinput
RUN chown webdev.webdev -R .
USER webdev
