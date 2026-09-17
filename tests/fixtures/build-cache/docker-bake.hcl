group "build" {
  targets = ["alpha", "beta"]
}

target "docker-metadata" {}

target "common" {
  inherits   = ["docker-metadata"]
  context    = "tests/fixtures/build-cache"
  dockerfile = "Dockerfile"
  platforms  = ["linux/amd64", "linux/arm64"]
}

target "alpha" {
  inherits = ["common"]
  args = { PACKAGE = "alpha" }
}

target "beta" {
  inherits = ["common"]
  args = { PACKAGE = "beta" }
}
