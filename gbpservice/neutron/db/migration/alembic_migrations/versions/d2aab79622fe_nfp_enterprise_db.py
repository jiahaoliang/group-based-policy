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

# revision identifiers, used by Alembic.
revision = 'd2aab79622fe'
down_revision = 'c1aab79622fe'

from alembic import op
import sqlalchemy as sa


def upgrade():
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
