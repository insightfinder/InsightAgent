FROM maven:3-eclipse-temurin as builder
WORKDIR /app
COPY . .
RUN mvn clean install -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN mkdir -p /app/config && mkdir -p /app/certs
COPY --from=builder /app/target/*.jar app.jar
COPY ./application.yml /app/config/application.yml
CMD java -jar app.jar --spring.config.location=file:/app/config/application.yml