group "build" {
  targets = ["mounts"]
}

target "docker-metadata" {}

target "mounts" {
  inherits   = ["docker-metadata"]
  context    = "tests/fixtures/build-cache"
  dockerfile = "Dockerfile.mounts"
  platforms  = ["linux/arm64"]
}
