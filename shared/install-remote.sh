#!/bin/bash

cd /root
tar xvf /tmp/$1 && cd $2
./install.sh --create
