plugins {
    `java-library`
    id("software.amazon.smithy.gradle.smithy-jar") version "1.5.0"
}

repositories {
    mavenCentral()
}

smithy {
    outputDirectory.set(file("../build/smithy"))
}

dependencies {
    smithyBuild("software.amazon.smithy:smithy-aws-traits:1.74.0")
    smithyBuild("software.amazon.smithy:smithy-openapi:1.74.0")
}
