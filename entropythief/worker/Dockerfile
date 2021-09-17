FROM python:3.9-slim
VOLUME /golem/output
COPY worker_public.py golem/run/
COPY randwrite.c golem/run/
RUN apt update
RUN apt-get -y install gcc 
RUN chmod +x golem/run/*
WORKDIR golem/run
RUN gcc randwrite.c -o worker

