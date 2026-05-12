## [7.2.2] - 2026-05-12

### 🐛 Bug Fixes

- *(promote)* Simplify release file fallback using /dev/null
## [7.2.1] - 2026-05-12

### 🐛 Bug Fixes

- *(promote)* Rename release-publish-enable and fix required file input
## [7.2.0] - 2026-05-12

### 🚀 Features

- *(promote)* Replace release-publish with svenstaro/upload-release-action
## [7.1.0] - 2026-05-12

### 🚀 Features

- *(promote)* Replace requarks/changelog-action with orhun/git-cliff-action
- *(promote)* Add changelog-prepend input for git-cliff prepend mode

### 🐛 Bug Fixes

- Add CHANGELOG.md

### 🚜 Refactor

- *(release-changelog)* Replace jx-changelog with requarks/changelog-action
## [7.0.6-prerelease] - 2026-05-12

### 🚀 Features

- *(actions)* Add release-changelog action using jx-changelog
- *(actions)* Add image/tag inputs, structured prepend, and changelog file tracking
- *(actions)* Add draft input to release-changelog action
- *(workflows)* Opt in to changelog on release, disable by default in promote
- *(actions)* Add release-publish action, decouple from changelog generation
- *(release)* Publish release
- *(release-version)* Add version-tag-prefix input
- *(release-version)* Auto-resolve previous-version from release branch
- *(release-version)* Add previous version output

### 🐛 Bug Fixes

- *(actions)* Default draft to true, optimize capture step
- Add prerelease versions
- Set jx changelog correct args
## [7.0.5] - 2026-05-05

### ⚙️ Miscellaneous Tasks

- Update action versions
- Bump version to v7.0.5
## [7.0.4] - 2026-05-05

### ⚙️ Miscellaneous Tasks

- Update action versions
- Bump version to v7.0.4
## [7.0.3] - 2026-05-05

### 🐛 Bug Fixes

- *(build)* Add prepare runner override

### ⚙️ Miscellaneous Tasks

- Bump version to v7.0.3
## [7.0.2] - 2026-05-05

### ⚙️ Miscellaneous Tasks

- Bump version to v7.0.2

### ◀️ Revert

- "fix(release-version): install qemu if not amd64"
- "fix(build): default reusable workflow runner to arm"
## [7.0.1] - 2026-05-05

### 🐛 Bug Fixes

- *(release-version)* Install qemu if not amd64

### ⚙️ Miscellaneous Tasks

- Update qemu action version
- Bump version to v7.0.1
## [7.0.0] - 2026-05-05

### 🐛 Bug Fixes

- *(release)* Push tag-triggered release commits to default branch

### ⚙️ Miscellaneous Tasks

- Bump version to v7.0.0
## [7.0.0-prerelease] - 2026-05-05

### 🐛 Bug Fixes

- *(build)* Make image build runners architecture-specific
- *(build)* Default reusable workflow runner to arm
## [6.7.5] - 2026-04-27

### ⚙️ Miscellaneous Tasks

- Update setup-just action
- Bump version to v6.7.5
## [6.7.4] - 2026-04-14

### 🐛 Bug Fixes

- *(command-action)* Upload artifacts on failure but skip cancelled runs

### ⚙️ Miscellaneous Tasks

- Bump version to v6.7.4
## [6.7.3] - 2026-04-04

### 🚜 Refactor

- *(build)* Align runner default input names

### ⚙️ Miscellaneous Tasks

- Bump version to v6.7.3
## [6.7.2] - 2026-04-04

### 🚜 Refactor

- *(build)* Add explicit runner fallback overrides for build, pre, and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v6.7.2
## [6.7.1] - 2026-03-30

### 🐛 Bug Fixes

- *(pr-create)* Set default value

### ⚙️ Miscellaneous Tasks

- Bump version to v6.7.1
## [6.7.0] - 2026-03-26

### 🚀 Features

- Update github script action version

### ⚙️ Miscellaneous Tasks

- Bump version to v6.7.0
## [6.6.2] - 2026-03-26

### 🚀 Features

- *(test/label)* Add post-comment input to control PR commenting

### 🚜 Refactor

- *(test)* Add option to disable comment on label check

### ⚙️ Miscellaneous Tasks

- Bump version to v6.6.1
- Bump version to v6.6.2
## [6.6.0] - 2026-02-23

### 🚀 Features

- *(promote)* Set version output

### ⚙️ Miscellaneous Tasks

- Bump version to v6.6.0
## [6.5.1] - 2026-02-23

### 🐛 Bug Fixes

- *(build)* Set version output

### ⚙️ Miscellaneous Tasks

- Bump version to v6.5.1
## [6.5.0] - 2026-02-23

### 🚀 Features

- Add all-green workflow

### 🚜 Refactor

- *(test)* Add detail in comment

### ⚙️ Miscellaneous Tasks

- Bump version to v6.5.0
## [6.4.0] - 2026-02-22

### 🚀 Features

- *(pr-create)* Use ubuntu 24.04 arm64 runner by default

### ⚙️ Miscellaneous Tasks

- Bump version to v6.4.0
## [6.3.2] - 2026-02-20

### 🚜 Refactor

- *(test)* Move action

### ⚙️ Miscellaneous Tasks

- Bump version to v6.3.2
## [6.3.1] - 2026-02-20

### 🚜 Refactor

- *(test)* Restructure actions

### ⚙️ Miscellaneous Tasks

- Bump version to v6.3.1
## [6.3.0] - 2026-02-20

### 🚀 Features

- *(pr-job-rerun)* Add output

### ⚙️ Miscellaneous Tasks

- Bump version to v6.3.0
## [6.2.6] - 2026-02-20

### 🚜 Refactor

- *(pr-job-rerun)* Run failed, all or a job

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.6
## [6.2.5] - 2026-02-20

### 🐛 Bug Fixes

- *(pr-reruns)* Use right endpoint

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.5
## [6.2.4] - 2026-02-19

### 🐛 Bug Fixes

- *(pr)* Avoid endless waiting

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.4
## [6.2.3] - 2026-02-19

### 🚜 Refactor

- Simplify version bumping in files

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.3
## [6.2.2] - 2026-02-19

### 🚜 Refactor

- *(pr)* Rename input

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.2
## [6.2.1] - 2026-02-19

### 🐛 Bug Fixes

- *(test)* Set default value

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.1
## [6.2.0] - 2026-02-19

### 🚀 Features

- Add test actions

### 🚜 Refactor

- *(release)* Rename secret

### ⚙️ Miscellaneous Tasks

- Bump version to v6.2.0
## [6.1.1] - 2026-02-19

### 🐛 Bug Fixes

- *(release-git-push)* Set version prefix

### ⚙️ Miscellaneous Tasks

- Bump version to 6.1.1
## [6.1.0] - 2026-02-19

### 🚀 Features

- Add all-green action
- Add checks rerun  action

### ⚙️ Miscellaneous Tasks

- Bump version to 6.1.0
## [6.0.4] - 2026-02-16

### 🚜 Refactor

- *(git-push)* Make push and tag atomic

### ⚙️ Miscellaneous Tasks

- Bump version to v6.0.4
## [6.0.3] - 2026-02-15

### 🐛 Bug Fixes

- *(promote)* Set package permissions
- *(relase)* Set package permissions

### ⚙️ Miscellaneous Tasks

- Bump version to v6.0.3
## [6.0.2] - 2026-02-15

### 🐛 Bug Fixes

- *(promote)* Add missing input

### ⚙️ Miscellaneous Tasks

- Bump version to v6.0.2
## [6.0.1] - 2026-02-15

### 🐛 Bug Fixes

- *(promote)* Add missing inputs

### ⚙️ Miscellaneous Tasks

- Bump version to v6.0.1
## [6.0.0] - 2026-02-15

### 🚀 Features

- *(promote)* Add promote image step

### 🐛 Bug Fixes

- *(promote)* Add note for package permissions

### 🚜 Refactor

- [**breaking**] Remove release workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v6.0.0
## [5.0.0] - 2026-02-15

### 🚀 Features

- *(bake)* Add commit-sha output

### 🐛 Bug Fixes

- *(bake)* Set image-digests output
- *(make)* Rename file

### 🚜 Refactor

- *(bake)* [**breaking**] Rename pull request as build workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v5.0.0
## [4.0.8] - 2026-02-15

### 🚀 Features

- *(bake)* Add additional tag input

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.8
## [4.0.7] - 2026-02-15

### 🚀 Features

- *(bake)* Add promote action

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.7
## [4.0.6] - 2026-02-15

### 🐛 Bug Fixes

- *(bake)* Add output to pull request

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.6
## [4.0.5] - 2026-02-15

### 🐛 Bug Fixes

- *(bake)* Set correct json format

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.5
## [4.0.4] - 2026-02-15

### 🐛 Bug Fixes

- *(bake)* Set correct json format

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.4
## [4.0.3] - 2026-02-15

### 🐛 Bug Fixes

- *(bake)* Set correct output

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.3
## [4.0.2] - 2026-02-15

### 🚜 Refactor

- *(bake)* Optimize step

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.2
## [4.0.1] - 2026-02-15

### 🚜 Refactor

- Do not store json file

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.1
## [4.0.0] - 2026-02-15

### 🐛 Bug Fixes

- [**breaking**] Rename version input names

### ⚙️ Miscellaneous Tasks

- Bump version to v4.0.0
## [3.0.0] - 2026-02-15

### 🚀 Features

- *(action)* Add metadata output

### 🐛 Bug Fixes

- Pass input for version output format
- Correct typo

### 🚜 Refactor

- [**breaking**] Rename version input names
- Use python for creating manifest list

### ⚙️ Miscellaneous Tasks

- Bump version to v3.0.0
## [2.0.0] - 2026-02-14

### 🚜 Refactor

- [**breaking**] Set docker login in pre and post steps as default

### ⚙️ Miscellaneous Tasks

- Bump version to v2.0.0
## [1.1.0] - 2026-02-14

### 🚀 Features

- Make docker login and qemu install optional in pre and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v1.1.0
## [1.0.1] - 2026-02-14

### 🐛 Bug Fixes

- Set not required

### ⚙️ Miscellaneous Tasks

- Bump version to v1.0.1
## [1.0.0] - 2026-02-14

### 🚀 Features

- [**breaking**] Add modules, fetch and tags arguments to checkout in workflows

### ⚙️ Miscellaneous Tasks

- Bump version to v1.0.0
## [0.4.18] - 2026-02-13

### 🐛 Bug Fixes

- Allow internal pipeline to modify workflow files when bumping versions

### ⚙️ Miscellaneous Tasks

- Add internal release pipeline
- Add checkout token
- Bump version to v0.4.18

### ◀️ Revert

- "fix: allow internal pipeline to modify workflow files when bumping versions"
## [0.4.17] - 2026-02-11

### 🚀 Features

- Add git-push option to promote workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.17
## [0.4.16] - 2026-01-29

### 🐛 Bug Fixes

- Set name of pre and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.16

### ◀️ Revert

- "fix: set name of pre and post steps"
## [0.4.15] - 2026-01-29

### 🐛 Bug Fixes

- Set name of pre and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.15
## [0.4.14] - 2026-01-29

### 🐛 Bug Fixes

- Set name of pre and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.14
## [0.4.13] - 2026-01-29

### 🐛 Bug Fixes

- Set name of pre and post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.13
## [0.4.12] - 2026-01-29

### 🐛 Bug Fixes

- Update conditional

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.12
## [0.4.11] - 2026-01-29

### 🐛 Bug Fixes

- Set conditional

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.11
## [0.4.10] - 2026-01-29

### 🐛 Bug Fixes

- Set dynamic job name

### 🚜 Refactor

- Remove redundant functions

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.10
## [0.4.9] - 2026-01-29

### 🐛 Bug Fixes

- Set default step name

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.9
## [0.4.8] - 2026-01-29

### 🚀 Features

- Get commit sha to release

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.8
## [0.4.7] - 2026-01-29

### 🚀 Features

- Get commit sha

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.7
## [0.4.6] - 2026-01-29

### 🚀 Features

- Ensure lowercase registry-image

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.6
## [0.4.5] - 2026-01-29

### 🐛 Bug Fixes

- Output matrix json

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.5
## [0.4.4] - 2026-01-29

### 🐛 Bug Fixes

- Handle especial chars better

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.4
## [0.4.3] - 2026-01-29

### 🚜 Refactor

- Use python for matrix generation

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.3
## [0.4.2] - 2026-01-29

### 🐛 Bug Fixes

- Set input as not required

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.2
## [0.4.1] - 2026-01-29

### 🚜 Refactor

- Set job name from matrix

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.1
## [0.4.0] - 2026-01-29

### 🚜 Refactor

- Add pre and post tests

### ⚙️ Miscellaneous Tasks

- Bump version to v0.4.0
## [0.3.31] - 2026-01-29

### 🚜 Refactor

- Set registry defaults

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.31
## [0.3.30] - 2026-01-29

### 🚜 Refactor

- Set default value

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.30
## [0.3.29] - 2026-01-29

### 🐛 Bug Fixes

- Set default value for secret

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.29
## [0.3.28] - 2026-01-29

### 🐛 Bug Fixes

- Set default value for secret

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.28
## [0.3.27] - 2026-01-29

### 🐛 Bug Fixes

- Set default if secret not set

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.27
## [0.3.26] - 2026-01-29

### 🐛 Bug Fixes

- Set secret as not required

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.26
## [0.3.25] - 2026-01-28

### 🚀 Features

- Add checkout token option

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.25
## [0.3.24] - 2026-01-28

### ⚙️ Miscellaneous Tasks

- Bump checkout action version
- Bump version to v0.3.24
## [0.3.23] - 2026-01-15

### 🐛 Bug Fixes

- Avoid error due to unescape char

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.23
## [0.3.22] - 2025-10-22

### 🚀 Features

- *(bake)* Relocate space cleanup action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.22
## [0.3.21] - 2025-08-26

### 🚜 Refactor

- *(buildx-bake)* Rename step

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.21
## [0.3.20] - 2025-08-26

### 🚀 Features

- *(buildx-bake)* Add cache mounts

### 🚜 Refactor

- Remove type from action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.20
## [0.3.19] - 2025-08-12

### 🐛 Bug Fixes

- Add inputs prefix

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.19
## [0.3.18] - 2025-08-12

### 🐛 Bug Fixes

- Use single quotes

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.18
## [0.3.17] - 2025-08-06

### 🚀 Features

- *(pr-create)* Add draft input

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.17
## [0.3.16] - 2025-08-06

### 🚜 Refactor

- Add names

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.16
## [0.3.15] - 2025-08-05

### 🚀 Features

- *(pr-create)* Add base branch to checkout

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.15
## [0.3.14] - 2025-07-29

### 🚜 Refactor

- Name source code artifact name

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.14
## [0.3.13] - 2025-07-29

### 🐛 Bug Fixes

- Use secret

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.13
## [0.3.12] - 2025-07-29

### 🚀 Features

- Add docker login to post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.12
## [0.3.11] - 2025-07-29

### 🐛 Bug Fixes

- Use literal commands

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.11
## [0.3.10] - 2025-07-29

### 🐛 Bug Fixes

- Use failure when skip

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.10
## [0.3.9] - 2025-07-29

### 🚀 Features

- Add default tags

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.9
## [0.3.8] - 2025-07-29

### 🚀 Features

- Add gha cache

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.8
## [0.3.7] - 2025-07-29

### 🚀 Features

- Add long sha

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.7
## [0.3.6] - 2025-07-29

### 🚀 Features

- Add docker login to post steps

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.6
## [0.3.5] - 2025-07-29

### 🚀 Features

- Add platform env

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.5
## [0.3.4] - 2025-07-29

### 🐛 Bug Fixes

- Add bake file

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.4
## [0.3.3] - 2025-07-28

### 🐛 Bug Fixes

- Set action source

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.3
## [0.3.2] - 2025-07-28

### 🚜 Refactor

- Set action path

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.2
## [0.3.1] - 2025-07-28

### 🚜 Refactor

- Update same repo action path

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.1
## [0.3.0] - 2025-07-28

### 🚀 Features

- Add multi runner docker bake builds
- Add command action

### 🚜 Refactor

- Use multi runner pr

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.0
## [0.3.0-prerelease] - 2025-07-28

### 🚜 Refactor

- *(bake)* [**breaking**] Rename registry image input

### ⚙️ Miscellaneous Tasks

- Bump version to v0.3.0-prerelease
## [0.2.22] - 2025-07-25

### 🚜 Refactor

- *(pull-request)* Remove unneeded env vars

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.22
## [0.2.21] - 2025-07-25

### 🚜 Refactor

- Use read for content in pull-request
- *(release)* Allow explicit command pre build
- *(pull-request)* Allow explicit command pre build
- Add more steps to release
- Add more steps to pull-request

### ⚙️ Miscellaneous Tasks

- Update versions in pull request
- Bump version to v0.2.21
## [0.2.20] - 2025-07-24

### 🚀 Features

- Add pull-request action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.20
## [0.2.19] - 2025-07-01

### 🐛 Bug Fixes

- *(pr-create)* Set branch name

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.19
## [0.2.18] - 2025-07-01

### 🚜 Refactor

- Fix pr-create workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.18
## [0.2.17] - 2025-07-01

### 🐛 Bug Fixes

- Set key name

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.17
## [0.2.16] - 2025-07-01

### 🚜 Refactor

- Convert pr-create to workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.16
## [0.2.15] - 2025-07-01

### 🚀 Features

- *(pr-create)* Set command as required

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.15
## [0.2.14] - 2025-07-01

### 🚀 Features

- Add pr-create composite action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.14
## [0.2.13] - 2025-05-22

### 🚀 Features

- Add option to free space in release

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.13
## [0.2.12] - 2025-05-09

### 🐛 Bug Fixes

- Push when only tag

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.12
## [0.2.11] - 2025-05-09

### 🚜 Refactor

- Do not require files to be added by git

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.11
## [0.2.10] - 2025-05-09

### 🐛 Bug Fixes

- Handle empty commits

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.10
## [0.2.9] - 2025-05-09

### 🚀 Features

- *(bake)* Add image name env var

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.9
## [0.2.8] - 2025-05-09

### 🚀 Features

- Add docker qemu to release action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.8
## [0.2.7] - 2025-05-09

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.7
## [0.2.6] - 2025-05-09

### 🚜 Refactor

- Change github org

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.6
## [0.2.5] - 2025-01-09

### 🐛 Bug Fixes

- *(release)* Add package lock option

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.5
## [0.2.4] - 2025-01-09

### 🚀 Features

- *(version-file)* Add package lock option

### 🚜 Refactor

- Make git add files required

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.4
## [0.2.3] - 2025-01-03

### 🚜 Refactor

- Use capitalization in step names

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.3
## [0.2.2] - 2024-12-30

### 🚀 Features

- Add bake set default values

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.2
## [0.2.1] - 2024-12-30

### 🐛 Bug Fixes

- Add bake set and push to release workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.1
## [0.2.0] - 2024-12-30

### 🚀 Features

- Add bake set

### ⚙️ Miscellaneous Tasks

- Bump version to v0.2.0
## [0.1.2] - 2024-12-26

### 🚀 Features

- *(release)* Add version output

### ⚙️ Miscellaneous Tasks

- Bump version to v0.1.2
## [0.1.1] - 2024-12-24

### 🐛 Bug Fixes

- *(version)* Use quotes for justfile

### ⚙️ Miscellaneous Tasks

- Bump version to v0.1.1
## [0.1.0] - 2024-12-24

### 🚜 Refactor

- Use github action to install just
- *(version)* Use value from input as file names

### ⚙️ Miscellaneous Tasks

- Bump version to v0.1.0
## [0.0.23] - 2024-12-24

### 🚀 Features

- *(release)* Add just hooks

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.23
## [0.0.22] - 2024-12-24

### 🚀 Features

- *(buildx-bake)* Add var to set extra bake files

### 🚜 Refactor

- *(release)* Convert node release to a generic release workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.22
## [0.0.21] - 2024-12-24

### 🐛 Bug Fixes

- Add correct target

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.21
## [0.0.20] - 2024-12-24

### 🐛 Bug Fixes

- Use correct target

### 🚜 Refactor

- Set default registry username

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.20
## [0.0.19] - 2024-12-24

### 🐛 Bug Fixes

- Set registry pass as secret

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.19
## [0.0.18] - 2024-12-24

### 🚜 Refactor

- Set username and pass default values

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.18
## [0.0.17] - 2024-12-23

### 🚜 Refactor

- Add meta tags

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.17
## [0.0.16] - 2024-12-23

### 🐛 Bug Fixes

- Remove unneeded id
- Set bake target

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.16
## [0.0.15] - 2024-12-23

### 🐛 Bug Fixes

- Remove unneeded id

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.15
## [0.0.14] - 2024-12-23

### 🚀 Features

- Set default image name

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.14
## [0.0.13] - 2024-12-23

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.13
## [0.0.12] - 2024-12-23

### 🚀 Features

- Add release git push action

### 🚜 Refactor

- Use release git push action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.12
## [0.0.11] - 2024-12-23

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.11
## [0.0.10] - 2024-12-23

### 🚜 Refactor

- Use local action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.10
## [0.0.9] - 2024-12-23

### 🚀 Features

- Add node release workflow

### 🚜 Refactor

- Rename buildx bake action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.9
## [0.0.8] - 2024-12-23

### 🚀 Features

- Add buildx bake action

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.8
## [0.0.7] - 2024-12-23

### 🚀 Features

- Add buildx bake workflow

### ⚙️ Miscellaneous Tasks

- Bump version to v0.0.7
## [0.0.6] - 2024-12-23

### ⚙️ Miscellaneous Tasks

- Add missing inputs
- Bump version to v0.0.6
## [0.0.5] - 2024-12-23

### 🐛 Bug Fixes

- Use conditional
## [0.0.4] - 2024-12-23

### 🚜 Refactor

- Use dash in input names

### ⚙️ Miscellaneous Tasks

- Add release pipeline
- Bump version
## [0.0.3] - 2024-12-23

### 🚀 Features

- Add script version

### 🚜 Refactor

- Use lower case for inputs
## [0.0.2] - 2024-12-17

### 🚀 Features

- Add promote and golint workflows
## [0.0.1] - 2024-12-17

### 🚀 Features

- Add release version action
- Add license
