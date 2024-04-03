FROM maven:3-eclipse-temurin as builder
WORKDIR /app
COPY . .
RUN mvn clean install -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN apk update && \
    apk add --no-cache openssl
RUN mkdir -p /app/config && mkdir -p /app/certs && mkdir /app/certs/sp
COPY --from=builder /app/target/*.jar app.jar
COPY ./application.yml /app/config/application.yml
COPY ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["sh", "/app/entrypoint.sh"]