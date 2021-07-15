FROM python:slim
VOLUME golem/output
COPY worker.py golem/run/
RUN apt update
RUN apt-get -y install build-essential
RUN pip3 install il
RUN chmod +x golem/run/*
