FROM alpine:latest
VOLUME /golem/output
COPY worker_public.py /golem/run/
COPY randwrite.c /golem/run/
RUN apk update && \
	apk add --no-cache --virtual virtgcc gcc musl-dev && \
	cd /golem/run && \
	gcc randwrite.c -o worker && \
	chmod +x /golem/run/worker && \
	apk del virtgcc && \
	rm -rf /var/cache/* 
