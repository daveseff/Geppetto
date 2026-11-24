

def test_rejects_multiple_authorized_keys_in_conditional_hook(tmp_path):
    import pytest
    from geppetto_automation.inventory import InventoryLoader
    path = tmp_path / 'invalid.fops'
    path.write_text("""node 'local' { connection => local }
task 'demo' on 'local' {
  exec { 'parent': command => 'true'
    on_success => {
      authorized_key { 'ansible': user => 'ansible'
        key => 'ssh-rsa AAA
ssh-ed25519 BBB'
      }
    }
  }
}
""")
    with pytest.raises(ValueError, match="ansible.*exactly one SSH public key"):
        InventoryLoader().load(path)
