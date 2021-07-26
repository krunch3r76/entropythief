FROM python:3.9-slim
VOLUME /golem/output
COPY worker.py golem/run/
COPY rdrand.c golem/run/
COPY build.sh golem/run/
RUN apt update
RUN apt-get -y install gcc 
# RUN apt-get -y install build-essential
RUN apt-get -y install python3-dev
RUN chmod +x golem/run/*
WORKDIR golem/run
# RUN cd /golem/run
RUN /golem/run/build.sh

