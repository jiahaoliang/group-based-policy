Run the follwing script on top of devstack Installation(Installed devstack should contain OC configuration changes and NoopFirewall driver plugin)

1. cd devstack

2. sudo bash <GBP_SCRIPT_PATH>/configure_oc_gbp_params.sh <GBP_SCRIPT_PATH> <devstack DIR PATH>
 
    e.g sudo bash GBP_SCRIPT/configure_oc_gbp_params.sh GBP_SCRIPT /home/stack/devstack 

3. sudo bash <GBP_SCRIPT_PATH>/wakeup_service.sh <CONFIGURATOR QCow2 Image> <GBP_SCRIPT_PATH> <devstack DIR_PATH>

    e.g sudo bash GBP_SCRIPT/wakeup_service.sh configurat_snapshot_with_docker_run GBP_SCRIPT /home/stack/devstack

