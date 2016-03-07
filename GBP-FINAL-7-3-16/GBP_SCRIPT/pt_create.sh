#! /bin/bash
set -x

GROUP=$1
NAME=$2

PORT=$(gbp policy-target-create --policy-target-group $GROUP $NAME | grep port_id  | awk '{print $4}')

nova boot --flavor m1.small --image e2e79636-67b7-4fff-9b5b-24eaecce0005 --nic port-id=$PORT $NAME
