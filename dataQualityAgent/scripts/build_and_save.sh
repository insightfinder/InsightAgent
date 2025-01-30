#!/bin/bash

docker build -t insightfinderinc/data-quality-agent .

rm data-quality-agent.tar 2>/dev/null

docker save insightfinderinc/data-quality-agent -o data-quality-agent.tar
