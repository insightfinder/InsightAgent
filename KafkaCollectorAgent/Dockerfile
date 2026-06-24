FROM maven:3.8-openjdk-8 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

FROM eclipse-temurin:8-jre
WORKDIR /app
COPY --from=builder /build/target/KafkaCollectorAgent-*.jar app.jar
COPY logback.xml logback.xml
COPY config.properties config.properties

ENTRYPOINT ["java", "-jar", "app.jar", \
  "--spring.config.location=file:/app/config.properties", \
  "--logging.config=file:/app/logback.xml"]
