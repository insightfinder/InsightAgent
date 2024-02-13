FROM maven:3-eclipse-temurin as builder
WORKDIR /app
COPY . .
RUN mvn clean install -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN mkdir -p /app/config
RUN mkdir -p /app/saml_cert
COPY --from=builder /app/target/*.jar app.jar
COPY ./application.yml /app/config/application.yml
COPY ./saml_cert/* /app/saml_cert/
CMD java -jar app.jar --spring.config.location=file:/app/config/application.yml