FROM maven:3.8-openjdk-8 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

FROM eclipse-temurin:8-jre

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/target/KafkaCollectorAgent-*.jar app.jar
COPY logback.xml logback.xml
COPY config.properties config.properties

RUN groupadd -r -g 10001 kafka-agent && \
    useradd -r -u 10001 -g kafka-agent -s /sbin/nologin kafka-agent && \
    mkdir -p logs && \
    chown -R kafka-agent:kafka-agent /app

USER kafka-agent

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-jar", "app.jar", \
  "--spring.config.location=file:/app/config.properties", \
  "--logging.config=file:/app/logback.xml"]
