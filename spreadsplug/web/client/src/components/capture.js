/** @jsx React.DOM */
/* global module, require, console */
(function() {
  'use strict';

  var React = require('react/addons'),
      foundation = require('./foundation.js'),
      ModelMixin = require('../../lib/backbonemixin.js'),
      LoadingOverlay = require('./overlays.js').Activity,
      lightbox = require('./overlays.js').LightBox,
      row = foundation.row,
      column = foundation.column,
      fnButton = foundation.button;


  /**
   * Screen component to control the capture process.
   *
   * @property {Workflow} workflow - Workflow to control capture on
   */
  module.exports = React.createClass({
    displayName: "CaptureScreen",

    /** Enables two-way databinding with Backbone model */
    mixins: [ModelMixin],

    /** Activates databinding for `workflow` model property. */
    getBackboneModels: function() {
      return [this.props.workflow];
    },
    getInitialState: function() {
      return {
        /** Display activity overlay? */
        waiting: false,
        /** Initial number of pages shot */
        initialPageCount: this.props.workflow.get('images').length,
        /** Message for activity overlay */
        waitMessage: undefined,
        /** Time of first capture */
        captureStart: undefined };
    },
    /**
     * Triggers preparation of capture on workflow and displays the activity
     * overlay until the process is finished.
     */
    componentWillMount: function() {
      this.toggleWaiting("Please wait while the devices  are being prepared " +
                          "for capture");
      this.props.workflow.prepareCapture(this.toggleWaiting);
    },
    /**
     * Triggers finish of capture on workflow.
     */
    componentWillUnmount: function() {
      console.log("Wrapping up capture process");
      this.props.workflow.finishCapture();
    },
    /**
     * Trigger a single capture, display activity overlay until it is finished
     */
    handleCapture: function() {
      console.log("Triggering capture");
      this.toggleWaiting("Please wait for the capture to finish...");
      this.props.workflow.triggerCapture(false, function() {
        this.toggleWaiting();
        if (this.state.refreshReview) {
          this.setState({refreshReview: false});
        }
      }.bind(this));
    },
    /**
     * Trigger a retake (= delete last <num_devices> captures and take new
     * ones, display activity overlay until it is finished.
     */
    handleRetake: function() {
      console.log("Re-taking last shot");
      this.toggleWaiting("Please wait for the capture to finish...");
      this.props.workflow.triggerCapture(true, function() {
        this.toggleWaiting();
        if (!this.state.refreshReview) {
          this.setState({refreshReview: true});
        }
      }.bind(this));
    },
    /**
     * Finish capture and navigate back to workflow list screen
     */
    handleFinish: function() {
      window.router.navigate('/', {trigger: true});
    },
    /**
     * Toggle display of activity overlay.
     *
     * @param {string} message - Message to display on overlay
     */
    toggleWaiting: function(message) {
      if (!this.state.waiting) {
        this.setState({
          waiting: true,
          waitMessage: message || ''
        });
      } else {
        this.setState({waiting: false});
      }
    },
    /**
     * Open image in lightbox overlay
     *
     * @param {url} - Image to display in lightbox
     */
    openLightbox: function(img) {
      this.setState({
        lightboxImage: img
      });
    },
    /**
     * Close the lightbox overlay.
     */
    closeLightbox: function() {
      this.setState({
        lightboxImage: undefined,
        refreshReview: false,
      });
    },
    render: function() {
      var workflow = this.props.workflow || {},
          randomSuffix = this.state.refreshReview ? '?'+(Math.random()*10e3 | 0) : '',
          speed, oddImage, evenImage;
      if (workflow && this.state.captureStart) {
        var elapsed = (new Date().getTime()/1000) - this.state.captureStart,
            shot = workflow.get('images').length - this.state.initialPageCount;
        speed = (3600/elapsed)*shot | 0;
      } else {
        this.setState({captureStart: new Date().getTime()/1000});
        speed = 0.0;
      }
      if (workflow.get('images').length) {
        oddImage = workflow.get('images').slice(-2)[0];
        evenImage = workflow.get('images').slice(-2)[1];
      }

      return (
        <div>
          {/* Display loading overlay? */}
          {this.state.waiting && <LoadingOverlay message={this.state.waitMessage} />}
          {/* Display lightbox overlay? */}
          {this.state.lightboxImage &&
            <lightbox onClose={this.closeLightbox} src={this.state.lightboxImage} />}
          {/* Only display review images if there are images on the workflow */}
          {(oddImage && evenImage) &&
          <row>
            <column>
              {/* NOTE: We append a random suffix to the thumbnail URL to force
                *       the browser to load from the server and not from the cache.
                *       This is needed since the images might change on the server,
                *       e.g. after a retake. */}
              {/* Landscape layout */}
              <ul className="show-for-landscape small-block-grid-2 capture-preview">
                <li>
                  <a onClick={function(){this.openLightbox(oddImage+'?'+randomSuffix);}.bind(this)}>
                    <img src={oddImage+"/thumb?"+randomSuffix} />
                  </a>
                </li>
                <li>
                  <a onClick={function(){this.openLightbox(evenImage+'?'+randomSuffix);}.bind(this)}>
                    <img src={evenImage+"/thumb?"+randomSuffix} />
                  </a>
                </li>
              </ul>
              {/* Portrait layout */}
              <ul className="show-for-portrait small-block-grid-1 medium-block-grid-2 capture-preview">
                  <li>
                    <a onClick={function(){this.openLightbox(oddImage+'?'+randomSuffix);}.bind(this)}>
                      <img src={oddImage+"/thumb?"+randomSuffix} />
                    </a>
                  </li>
                <li>
                  <a onClick={function(){this.openLightbox(evenImage+'?'+randomSuffix);}.bind(this)}>
                    <img src={evenImage+"/thumb?"+randomSuffix} />
                  </a>
                </li>
              </ul>
            </column>
          </row>}
          <row className="capture-info">
            <column size="6">
              <span className="pagecount">{workflow.get('images').length} pages</span>
            </column>
            {speed > 0 &&
            <column size="6">
              <span className="capturespeed">{speed} pages/hour</span>
            </column>}
          </row>
          <row>
            <div className="small-12 capture-controls columns">
              <ul>
                <li>
                  <fnButton callback={this.handleRetake} secondary='true' size='large'>
                      <i className="fi-refresh"></i>
                  </fnButton>
                </li>
                <li id="trigger-capture">
                  <fnButton callback={this.handleCapture} size='large'>
                    <i className="fi-camera"></i>
                  </fnButton>
                </li>
                <li>
                  <fnButton callback={this.handleFinish} secondary='true' size='large'>
                      <i className="fi-check"></i>
                  </fnButton>
                </li>
              </ul>
            </div>
          </row>
        </div>
      );
    }
  });
})();
