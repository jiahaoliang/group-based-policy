# Copyright 2016 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

"""nfp_db
Revision ID: 54ee8e8d205a
Revises: 3791adbf0045
"""


# revision identifiers, used by Alembic.
revision = '54ee8e8d205a'
down_revision = '3791adbf0045'


from alembic import op
import sqlalchemy as sa

from gbpservice.nfp.common import constants as nfp_constants


def upgrade():

    op.create_table(
        'nfp_port_infos',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('port_model',
                  sa.Enum(nfp_constants.NEUTRON_PORT,
                          nfp_constants.GBP_PORT,
                          name='port_model'),
                  nullable=False),
        sa.Column('port_classification',
                  sa.Enum(nfp_constants.PROVIDER,
                          nfp_constants.CONSUMER,
                          nfp_constants.MANAGEMENT,
                          nfp_constants.MONITOR,
                          name='port_classification'),
                  nullable=False),
        sa.Column('port_role',
                  sa.Enum(nfp_constants.ACTIVE_PORT,
                          nfp_constants.STANDBY_PORT,
                          nfp_constants.MASTER_PORT,
                          name='port_role'),
                  nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'nfp_network_infos',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('network_model',
                  sa.Enum(nfp_constants.NEUTRON_NETWORK,
                          nfp_constants.GBP_NETWORK,
                          name='network_model'),
                  nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'nfp_network_functions',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=1024), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('status_description', sa.String(length=255), nullable=True),
        sa.Column('service_id', sa.String(length=36), nullable=False),
        sa.Column('service_chain_id', sa.String(length=36), nullable=False),
        sa.Column('service_profile_id', sa.String(length=36), nullable=True),
        sa.Column('service_config', sa.TEXT(), nullable=True),
        sa.Column('heat_stack_id', sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'nfp_network_function_devices',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('status_description', sa.String(length=255), nullable=True),
        sa.Column('mgmt_ip_address', sa.String(length=36), nullable=True),
        sa.Column('mgmt_port_id',
                  sa.String(length=36),
                  nullable=True),
        sa.Column('monitoring_port_id',
                  sa.String(length=36),
                  nullable=True),
        sa.Column('monitoring_port_network',
                  sa.String(length=36),
                  nullable=True),
        sa.Column('service_vendor', sa.String(length=36), nullable=True),
        sa.Column('max_interfaces', sa.Integer(), nullable=True),
        sa.Column('reference_count', sa.Integer(), nullable=True),
        sa.Column('interfaces_in_use', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['mgmt_port_id'],
                                ['nfp_port_infos.id'],
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['monitoring_port_network'],
                                ['nfp_network_infos.id'],
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['monitoring_port_id'],
                                ['nfp_port_infos.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'nfp_network_function_instances',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('status_description', sa.String(length=255), nullable=True),
        sa.Column('ha_state', sa.String(length=50), nullable=True),
        sa.Column('network_function_id', sa.String(length=36), nullable=True),
        sa.Column('network_function_device_id',
                  sa.String(length=36),
                  nullable=True),
        sa.ForeignKeyConstraint(['network_function_device_id'],
                                ['nfp_network_function_devices.id'],
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['network_function_id'],
                                ['nfp_network_functions.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'nfp_nfi_dataport_associations',
        sa.Column('network_function_instance_id',
                  sa.String(length=36),
                  nullable=True),
        sa.Column('data_port_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['network_function_instance_id'],
                                ['nfp_network_function_instances.id']),
        sa.ForeignKeyConstraint(['data_port_id'], ['nfp_port_infos.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('network_function_instance_id', 'data_port_id')
    )

    op.create_table(
        'nfp_network_function_device_interfaces',
        sa.Column('tenant_id', sa.String(length=255), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('plugged_in_port_id', sa.String(length=36), nullable=True),
        sa.Column('interface_position',
                  sa.Integer(),
                  nullable=True),
        sa.Column('mapped_real_port_id', sa.String(length=36), nullable=True),
        sa.Column('network_function_device_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['plugged_in_port_id'],
                                ['nfp_port_infos.id'],
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['network_function_device_id'],
                                ['nfp_network_function_devices.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    pass
