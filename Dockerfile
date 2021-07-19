FROM python:slim
VOLUME /golem/output
COPY worker.py golem/run/
RUN apt update
RUN chmod +x golem/run/*
