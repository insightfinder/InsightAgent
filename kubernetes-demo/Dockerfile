FROM python:3
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY main.py /usr/src/app
ENV DATABASE_URL=""
RUN pip install psycopg2-binary
ENTRYPOINT ["python", "./main.py"]