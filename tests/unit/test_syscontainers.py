#pylint: skip-file

import os
import shutil
import tempfile
import unittest
import subprocess
import json

from Atomic import util
from Atomic.syscontainers import SystemContainers


no_mock = True
try:
    from unittest.mock import ANY, patch, call
    no_mock = False
except ImportError:
    try:
        from mock import ANY, patch, call
        no_mock = False
    except ImportError:
        # Mock is already set to False
        pass

if no_mock:
    # If there is no mock, we need need to create a fake
    # patch decorator
    def fake_patch(a, new=''):
        def foo(func):
            def wrapper(*args, **kwargs):
                ret = func(*args, **kwargs)
                return ret
            return wrapper
        return foo

    patch = fake_patch

@unittest.skipIf(no_mock, "Mock not found")
class TestSystemContainers_do_checkout(unittest.TestCase):
    """
    Unit tests for refactored function from SystemContainers.do_checkout method.
    """
    def test_get_remote_location(self):
        """
        This function checks for 4 different cases of _get_remote_location function
        1: when the remote is given as /xx and /xx/rootfs exist
        2: when the remote is given as /xx/rootfs and /xx/rootfs/usr exist
        3: when the remote input does not contain a rootfs
        4: when the remote input path does not exist
        """
        try:
            tmpdir = tempfile.mkdtemp()
            rootfs_location = os.path.sep.join([tmpdir, "rootfs"])
            not_valid_location = os.path.sep.join([tmpdir, "not-valid-test"])
            non_existant_location = os.path.sep.join([tmpdir, "non-existant-path"])

            os.makedirs(os.path.sep.join([rootfs_location, "usr"]))
            os.mkdir(not_valid_location)

            # Here: we check for 4 different cases _get_remote_location verifies
            self.assertRaises(ValueError, SystemContainers._get_remote_location, non_existant_location)

            remote_path_one = SystemContainers._get_remote_location(tmpdir)
            # we default to real path here because on AH, / sometimes actually refer to /sysroot
            self.assertEqual(remote_path_one, os.path.realpath(tmpdir))

            remote_path_two = SystemContainers._get_remote_location(rootfs_location)
            self.assertEqual(remote_path_two, os.path.realpath(tmpdir))

            self.assertRaises(ValueError, SystemContainers._get_remote_location, not_valid_location)
        finally:
            # We then remove the directories to keep the user's fs clean
            shutil.rmtree(tmpdir)

    def test_prepare_rootfs_dirs(self):
        """
        This function checks for 3 different cases for function '_prepare_rootfs_dirs'
        1: extract specified with either destination/remote_path
        2: remote_path and destination specified
        3: only destination specified
        """

        try:
            # Prepare the temp location for verifying
            tmpdir = tempfile.mkdtemp()
            extract_location = os.path.sep.join([tmpdir, "extract"])
            remote_location  = os.path.sep.join([tmpdir, "remote"])
            remote_destination_case = os.path.sep.join([tmpdir, "dest_one"])
            destination_location = os.path.sep.join([tmpdir, "dest_two"])

            sc = SystemContainers()

            # Create expected rootfs for future comparison
            expected_remote_rootfs = os.path.join(remote_location, "rootfs")
            expected_dest_rootfs = os.path.join(destination_location, "rootfs")

            # Here, we begin testing 3 different cases mentioned above
            extract_rootfs = sc._prepare_rootfs_dirs(None, extract_location, extract_only=True)
            self.assertTrue(os.path.exists(extract_rootfs), True)
            self.assertEqual(extract_rootfs, extract_location)

            remote_rootfs = sc._prepare_rootfs_dirs(remote_location, remote_destination_case)
            self.assertEqual(remote_rootfs, expected_remote_rootfs)
            self.assertTrue(os.path.exists(remote_destination_case), True)

            # Note: since the location passed in is not in /var/xx format, canonicalize location
            # should not have an effect, thus we don't worry about it here
            destination_rootfs = sc._prepare_rootfs_dirs(None, destination_location)
            self.assertEqual(destination_rootfs, expected_dest_rootfs)
            self.assertTrue(os.path.exists(expected_dest_rootfs), True)

        finally:
            shutil.rmtree(tmpdir)

    def test_write_config_to_dest(self):
        """
        This function checks 3 different cases for function 'write_config_to_dest'
        1: checks when exports/config.json exist, the files are copied correctly
        2: checks exports/config.json.template exist, the template is copied, and values inside the template are swapped by values
        3: checks the  configuration was correct when the above 2 cases do not apply
        """

        def check_attr_in_json_file(json_file, attr_name, value, second_attr=None):
            # We don't check existance here, because in this context, files do exist
            with open(json_file, "r") as f:
                json_val = json.loads(f.read())
                actual_val =  json_val[attr_name][second_attr] if second_attr else json_val[attr_name]
                self.assertEqual(actual_val, value)

        try:
            # Prepare the temp directory for verification
            tmpdir = tempfile.mkdtemp()
            dest_location = os.path.sep.join([tmpdir, "dest"])
            dest_location_config = os.path.join(dest_location, "config.json")
            # Note: in this context, the location of exports should not matter, as we are only copying files from exports
            # in this function
            exports_location = os.path.join(tmpdir, "rootfs/exports")
            exports_json = os.path.join(exports_location, "config.json")

            os.makedirs(exports_location)
            os.mkdir(dest_location)
            values = {"test_one": "$hello_test"}
            with open(exports_json, 'w') as json_file:
                json_file.write(json.dumps(values, indent=4))
                json_file.write("\n")
            new_values = {"hello_test" : "new_val"}

            sc = SystemContainers()
            sc._write_config_to_dest(dest_location, exports_location)
            self.assertTrue(os.path.exists(dest_location_config), True)
            check_attr_in_json_file(dest_location_config, "test_one", "$hello_test")
            # We remove the file to keep the destination clean for next operation
            os.remove(dest_location_config)

            # Rename exports/config.json to exports/config.json.template
            os.rename(exports_json, exports_json + ".template")
            sc._write_config_to_dest(dest_location, exports_location, new_values)
            self.assertTrue(os.path.exists(dest_location_config), True)
            check_attr_in_json_file(dest_location_config, "test_one", "new_val")
            os.remove(dest_location_config)

            # Note: in this case, the configuration is generated and changed via 'generate_default_oci_configuration' which uses runc.
            # Thus, we assume when user tries to run the unit test with this function, he will have runc installed
            sc._write_config_to_dest(dest_location, os.path.join(tmpdir, "not_exist"))
            self.assertTrue(os.path.exists(dest_location_config), True)
            check_attr_in_json_file(dest_location_config, "root", "rootfs", second_attr="path")

        finally:
            shutil.rmtree(tmpdir)

    def test_get_manifest_attribtues(self):
        """
        This function checks 2 simple cases to verify the functionality of '_get_manifest_attribtues'
        1: When the attribute is not in the manifest, a default val should be returned
        2: When the key is there and manifest itself exist, its corresponding value should be returned
        """
        manifest = {"rename_files" : "test_val"}

        # Test for the two cases mentioned above
        test_val_one = SystemContainers._get_manifest_attributes(manifest, "rename_files", None)
        self.assertEqual(test_val_one, "test_val")

        test_val_two = SystemContainers._get_manifest_attributes(manifest, "non_existant", "test_two")
        self.assertEqual(test_val_two, "test_two")

    def test_update_rename_file_value(self):
        """
        This function checks 2 different cases for function '_update_rename_file_value'
        1: checks if the values will be successfully swapped given correct value combinations
        2: checks when one of the values in "rename_files" is not replaced, error will come out
        """

        # Prepare for the values
        sc = SystemContainers()
        manifest = {"renameFiles" : {"testKey" : "$testVal",
                                     "testKeySec" : "$testTwo"}}
        values =  {"testVal" : "testSubOne",
                    "testTwo" : "testSubTwo"}
        secondValues = {"testVal" : "secondTestSubOne"}

        # Test for the cases mentioned above
        sc._update_rename_file_value(manifest, values)
        self.assertEqual(manifest["renameFiles"]["testKey"], "testSubOne")
        self.assertEqual(manifest["renameFiles"]["testKeySec"], "testSubTwo")

        # Reset the value for next test case
        manifest["renameFiles"]["testKey"] = "$testMisMatch"
        self.assertRaises(ValueError, sc._update_rename_file_value, manifest, secondValues)

    def test_write_info_file(self):
        """
        This function checks 2 simple cases to verify functionality of '_write_info_file'
        1: When error occurs, the files specified in 'new_install_files' are removed
        2: Otherwise, the info file is written to the correct location
        """

        try:
            # Prepare directories and values
            tmpdir = tempfile.mkdtemp()
            installed_file = tempfile.mkstemp(prefix=tmpdir)
            installed_file_path = installed_file[1]
            destination_dir = os.path.sep.join([tmpdir, "dest_dir"])
            destination_info_path =  os.path.join(destination_dir, "info")

            options = {"destination" : destination_dir,
                       "prefix" : None,
                       "img" : "test",
                       "remote" : None,
                       "system_package" : "no",
                       "values" : {}}
            rpm_install_content = {"new_installed_files" : [installed_file_path],
                                   "rpm_installed" : False,
                                   "new_installed_files_checksum" : {}}

            # Since the destination is not created yet, we test here would result an IOError,
            # leading to the installed_file to be removed
            sc = SystemContainers()
            self.assertRaises(IOError, sc._write_info_file, options, None, rpm_install_content, None, None)
            self.assertFalse(os.path.exists(installed_file_path))

            os.mkdir(destination_dir)
            sc._write_info_file(options, None, rpm_install_content, None, None)
            self.assertTrue(os.path.exists(destination_info_path))

        finally:
            shutil.rmtree(tmpdir)

    @patch("Atomic.rpm_host_install.RPMHostInstall.generate_rpm")
    @patch("Atomic.rpm_host_install.RPMHostInstall.rm_add_files_to_host")
    @patch("Atomic.syscontainers.SystemContainers.inspect_system_image")
    def test_handle_system_package_files(self, _isi, _raf, _gr):
        """
        This function checks 3 simple cases to verify the basic functionality of handle_system_package_files
        1: When 'system_package = absent'
        2: When system_package is 'yes'
        3: When system_package='no'

        For 3 above cases, we verify if the expected outcome matches the actual outcome

        Do note, this is just testing the workflow on a higher level of the subsequent function calls. IOW, the lower level function
        call 'generate_rpm' or 'rm_add_files_to_host' will not be tested here (it is covered as a whole in integration test)
        """
        expected_checksum = {"test" : "test_checksum_xxx"}
        _gr.return_value = (True, "rpm_file", None)
        _raf.return_value = expected_checksum
        _isi.return_value = {"ImageId" : {}}
        manifest = {}

        # Note, even though we replace the return value, we still need to make sure
        # entries such as img or destination do exist in options to avoid key error
        options = {"system_package" : "yes",
                   "img" : None,
                   "destination" : "",
                   "values" : {},
                   "deployment" : 1,
                   "name" : "test"}
        test_options_two = {"system_package" : "no",
                            "installed_files_checksum": "",
                            "prefix" : "",
                            "values" : ""}
        test_options_third = {"system_package" : "absent"}

        sc = SystemContainers()
        rpm_install_output_one = sc._handle_system_package_files(test_options_third, manifest, "")
        self.assertEqual(rpm_install_output_one["new_installed_files_checksum"], {})

        rpm_install_output_second = sc._handle_system_package_files(options, manifest, "")
        self.assertEqual(rpm_install_output_second["rpm_installed"], True)

        rpm_install_output_third = sc._handle_system_package_files(test_options_two, manifest, "")
        self.assertEqual(rpm_install_output_third["new_installed_files_checksum"], expected_checksum)

@unittest.skipIf(no_mock, "Mock not found")
class TestSystemContainers_miscellaneous(unittest.TestCase):
    """
    Unit tests for general / utility functions in syscontainers.py
    """
    def test_encode_to_ostree_ref(self):
        """
        Verify that 1: image after encoded to ostree ref will be no longer hex
        2: image contains no tag will have tag latest appended
        3: qualified image(image with registry included) and non-qualified image will behave in the same way
        when calling _encode_to_ostree_ref
        """

        def ensure_ref_is_not_hex(ref):
            ref_is_hex = SystemContainers._is_hex(ref)
            self.assertFalse(ref_is_hex)

        qual_img_without_tag = "registry.fedoraproject.org/f27/kubernetes-apiserver"
        qual_img_with_tag = qual_img_without_tag + ":tag"
        non_qual_img_without_tag = "cafe"
        non_qual_img_with_tag = non_qual_img_without_tag + ":tag"

        qual_img_without_tag_ref = SystemContainers._encode_to_ostree_ref(qual_img_without_tag)
        self.assertTrue(qual_img_without_tag_ref.endswith("latest"))
        ensure_ref_is_not_hex(qual_img_without_tag_ref)

        # The encoded ref will have ":" translated to _3A (unicode)
        qual_img_with_tag_ref = SystemContainers._encode_to_ostree_ref(qual_img_with_tag)
        self.assertTrue(qual_img_with_tag_ref.endswith("_3Atag"))
        ensure_ref_is_not_hex(qual_img_with_tag_ref)

        non_qual_img_without_tag_ref = SystemContainers._encode_to_ostree_ref(non_qual_img_without_tag)
        ensure_ref_is_not_hex(non_qual_img_without_tag_ref)

        non_qual_img_with_tag_ref = SystemContainers._encode_to_ostree_ref(non_qual_img_with_tag)
        self.assertTrue(non_qual_img_with_tag_ref.endswith("_3Atag"))
        ensure_ref_is_not_hex(non_qual_img_with_tag_ref)

@unittest.skipIf(no_mock, "Mock not found")
class TestSystemContainers_container_exec(unittest.TestCase):
    """
    Unit tests for the SystemContainres.container_exec method.
    """

    class Args():
        """
        Fake argument object for use in tests.
        """
        def __init__(self, atomic_config=None, backend=None, user=False, args=None, setvalues=None, display=False):
            self.atomic_config = atomic_config or util.get_atomic_config()
            self.backend = backend
            self.user = user
            self.args = args or []
            self.setvalues = setvalues
            self.display = display

    def test_container_exec_in_usermode(self):
        """
        A ValueError should be raised as usermode is not supported.
        """
        args = self.Args(backend='ostree')
        sc = SystemContainers()
        sc.set_args(args)
        self.assertRaises(ValueError, sc.container_exec, 'test', False, {})

    @patch('Atomic.syscontainers.SystemContainers._is_service_active')
    @patch('Atomic.util.is_user_mode')
    @patch('Atomic.backendutils.BackendUtils.get_backend_and_container_obj')
    def test_container_exec_not_running_no_checkout(self, _gb, _um, _sa):
        """
        A ValueError should be raised when the container is not running and there is no checkout.
        """
        _sa.return_value = False  # The service is not active
        _um.return_value = False  # user mode is False
        _gb.return_value = None  # The checkout is None

        args = self.Args(backend='ostree')
        sc = SystemContainers()
        sc.set_args(args)
        self.assertRaises(ValueError, sc.container_exec, 'test', False, {})

    @patch('Atomic.syscontainers.SystemContainers._is_service_active')
    @patch('Atomic.util.is_user_mode')
    @patch('Atomic.syscontainers.SystemContainers._canonicalize_location')
    def test_container_exec_not_running_with_detach(self, _cl, _um, _sa):
        """
        A ValueError should be raised when the container is not running and detach is requested.
        """
        _sa.return_value = False  # The service is not active
        _um.return_value = False  # user mode is False
        _cl.return_value = "/var/lib/containers/atomic/test.0"  # Fake a checkout

        args = self.Args(backend='ostree')
        sc = SystemContainers()
        sc.set_args(args)
        self.assertRaises(ValueError, sc.container_exec, 'test', True, {})  # Run with detach as True

    @patch('Atomic.syscontainers.SystemContainers._is_service_active')
    @patch('Atomic.util.check_call')
    @patch('Atomic.util.is_user_mode')
    def test_container_exec_with_container_running(self, _um, _cc, _sa):
        """
        Expect the container exec command to be used when container is running.
        """
        cmd_call = [util.RUNC_PATH, 'exec', 'test']
        if os.isatty(0):  # If we are a tty then we need to pop --tty in there
            cmd_call.insert(2, '--tty')
        expected_call = call(cmd_call, stderr=ANY, stdin=ANY, stdout=ANY)

        _sa.return_value = True  # The service is active
        _um.return_value = False  # user mode is False
        args = self.Args(backend='ostree', user=False)
        sc = SystemContainers()
        sc.set_args(args)
        sc.container_exec('test', False, {})

        self.assertEqual(_cc.call_args, expected_call)

    @patch('Atomic.syscontainers.SystemContainers._is_service_active')
    @patch('subprocess.Popen')
    @patch('Atomic.util.is_user_mode')
    @patch('Atomic.syscontainers.SystemContainers._canonicalize_location')
    def test_container_exec_without_container_running(self, _ce, _um, _cc, _sa):
        """
        Expect the container to be started if it's not already running.
        """
        expected_args = [util.RUNC_PATH, 'run', 'test']

        _sa.return_value = False  # The service is not active
        _um.return_value = False  # user mode is False
        tmpd = tempfile.mkdtemp()
        try:
            _ce.return_value = tmpd  # Use a temporary directory for testing
            args = self.Args(backend='ostree', user=False)
            sc = SystemContainers()
            sc.set_args(args)

            shutil.copy('./tests/test-images/system-container-files-hostfs/config.json.template', os.path.join(tmpd, 'config.json'))

            sc.container_exec('test', False, {})
            self.assertEqual(_cc.call_args[0][0], expected_args)
        finally:
            shutil.rmtree(tmpd)


class TestSystemContainers_get_skopeo_args(unittest.TestCase):
    """
    Unit tests for the SystemContainres._get_skopeo_args method.
    """

    def setUp(self):
        self.sc = SystemContainers()

    def test_get_skopeo_args(self):
        """
        Verify _get_skopeo_args return proper data when passing in different image uris.
        """
        for test_image, expected_insecure, expected_image in (
                # Explicitly insecure
                ('http:docker.io/busybox:latest', True, 'docker.io/busybox:latest'),
                # Implicitly secure
                ('docker.io/busybox:latest', False, 'docker.io/busybox:latest'),
                ('https:docker.io/busybox:latest', False, 'docker.io/busybox:latest'),
                ('oci:docker.io/busybox:latest', False, 'docker.io/busybox:latest')):
            # Make the call
            insecure, image = self.sc._get_skopeo_args(test_image)
            # Verify the results
            self.assertEqual(expected_insecure, insecure)
            self.assertEqual(expected_image, image)

    # def test_get_skopeo_args_with_full_resolution(self):


if __name__ == '__main__':
    unittest.main()
