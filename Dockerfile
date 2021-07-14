FROM python:slim
VOLUME golem/output
COPY worker.py golem/run/
RUN pip install il
RUN chmod +x golem/run/*
